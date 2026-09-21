"""
亮点：端到端意图识别

识别策略：
  1. 关键词/短句规则优先—— 明确意图零 LLM 调用
  2. LLM + Embedding 兜底—— 仅处理模糊或复合表达

兜底阶段通过加权投票合并结果，置信度低于阈值时降级为 OTHER。
"""
import asyncio
import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from anthropic import AsyncAnthropic

from core.llm_utils import extract_text_content

logger = logging.getLogger(__name__)


class IntentCategory(Enum):
    EXPLAIN = "explain" #知识讲解
    QA = "qa" #学习答疑
    QUIZ = "quiz" #练习出题
    REVIEW = "review" #复习总结
    GREETING = "greeting" #问候
    OTHER      = "other"


class UrgencyLevel(Enum):
    LOW      = 1
    MEDIUM   = 2
    HIGH     = 3
    CRITICAL = 4


@dataclass
class IntentResult:
    intent:     IntentCategory
    confidence: float
    urgency:    UrgencyLevel
    entities:   Dict[str, List[str]]   # 从消息中提取的实体
    reasoning:  str
    latency_ms: float


# ── Few-shot 模板（同时用于 LLM 示例和 Embedding 匹配）────────────────────────
_TEMPLATES: Dict[IntentCategory, List[str]] = {
    IntentCategory.EXPLAIN:["给我讲一下","什么是","解释一下",],
    IntentCategory.QUIZ:["给我出一道题","考考我这类知识点","我想做一些练习",],
    IntentCategory.REVIEW:["帮我复习今天学过的内容","总结一下这一章","回顾一下我的薄弱点",],
    IntentCategory.GREETING:["你好","开始学习","今天学什么",],
}

# 紧急关键词
_URGENCY_KEYWORDS = {
    UrgencyLevel.CRITICAL: ["紧急", "emergency", "urgent", "asap", "立刻"],
    UrgencyLevel.HIGH:     ["今天", "马上", "尽快", "hurry", "now"],
    UrgencyLevel.MEDIUM:   ["这周", "soon", "快点"],
}


def _cosine(a: List[float], b: List[float]) -> float:
    """纯 Python 余弦相似度，不依赖 numpy。"""
    dot = sum(x * y for x, y in zip(a, b))
    na  = sum(x * x for x in a) ** 0.5
    nb  = sum(x * x for x in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


class IntentRecognizer:
    """
    端到端意图识别器。

    初始化时不加载任何本地模型，所有 AI 能力通过 Anthropic API 调用。
    模板 Embedding 在首次请求时懒加载并缓存，后续复用。
    """

    def __init__(
        self,
        api_key: str,
        base_url: Optional[str] = None,
        model: str = "claude-3-5-sonnet-20241022",
        confidence_threshold: float = 0.5,
    ):
        kwargs: Dict[str, Any] = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self.client    = AsyncAnthropic(**kwargs)
        self.model     = model
        self.threshold = confidence_threshold
        # 第三方兼容 API（如 DeepSeek）通常不支持 Embedding，禁用该策略。
        # 官方 Anthropic SDK 当前没有 embeddings 资源，因此下面会使用稳定的
        # 本地字符 n-gram 向量作为轻量兜底，保证三路融合链路真实可跑。
        self._embedding_enabled = not bool(base_url)

        #首次识别才会计算模板向量，由_load_template_embeddings方法进行编写
        self._tpl_embeddings: Dict[IntentCategory, List[List[float]]] = {}
        #缓存
        self._cache: Dict[str, IntentResult] = {}
        self.cache_hits   = 0
        self.cache_misses = 0

    # ── 公开接口 ──────────────────────────────────────────────────────────────
    # 流程：缓存查找 → 关键词规则优先 → 模糊输入使用 LLM/Embedding → 缓存结果
    async def recognize(
        self,
        message: str,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> IntentResult:
        """
        识别用户意图。

        history 格式：[{"role": "user"/"assistant", "content": "..."}]
        """
        key = self._cache_key(message,history)
        if key in self._cache:
            self.cache_hits += 1
            return self._cache[key]
        self.cache_misses += 1

        t0 = time.monotonic()

        pat = self._pattern_recognize(message)

        # 明确关键词且没有类别冲突时直接采用规则，不产生 LLM 请求。
        if pat["intent"] != IntentCategory.OTHER and pat["confidence"] >= 0.85:
            intent = pat["intent"]
            confidence = pat["confidence"]
            reasoning = pat.get("reasoning", "关键词规则命中")
        else:
            # 规则无法确定时，才并行执行 LLM 和轻量 Embedding 兜底。
            llm_task = asyncio.create_task(self._llm_recognize(message, history))
            emb_task = (
                asyncio.create_task(self._embedding_recognize(message))
                if self._embedding_enabled
                else None
            )

            if emb_task:
                llm, emb = await asyncio.gather(llm_task, emb_task)
            else:
                llm = await llm_task
                emb = {"intent": IntentCategory.OTHER, "confidence": 0.0}

            intent = self._vote(llm, emb, pat)
            confidence = self._result_confidence(intent, llm, emb, pat)
            reasoning = llm.get("reasoning", "")

        # MVP 阶段实体尚未参与路由和回答，暂停独立 LLM 实体提取。
        entities: Dict[str, List[str]] = {}
        urgency  = self._urgency(message, intent)

        result = IntentResult(
            intent=intent,
            confidence=confidence,
            urgency=urgency,
            entities=entities,
            reasoning=reasoning,
            latency_ms=(time.monotonic() - t0) * 1000,
        )

        # LRU 缓存
        if len(self._cache) >= 1000:
            for k in list(self._cache)[:500]:
                del self._cache[k]
        self._cache[key] = result
        return result

    def learn(self, message: str, correct: IntentCategory) -> None:
        """动态增加模板样本：将纠正样本加入模板，清除对应 Embedding 缓存。"""
        tpls = _TEMPLATES.setdefault(correct, [])
        if message not in tpls:
            tpls.append(message)
            self._tpl_embeddings.pop(correct, None)  # 下次重新计算
            logger.info(f"学习新样本 → {correct.value}: {message[:40]}")

    # ── 三路识别策略 ──────────────────────────────────────────────────────────

    async def _llm_recognize(
        self,
        message: str,
        history: Optional[List[Dict[str, str]]],
    ) -> Dict[str, Any]:
        """策略 1：LLM 语义理解（Few-shot + 上下文）。"""
        #流程：先构建提示词（Few-shot示例、上下文、）->调用大模型
        message = self._clean_text(message)
        # 构建 Few-shot 示例（只取模板的第一条）
        examples = "\n".join(
            f'  消息: "{t}" → 意图: {cat.value}'
            for cat, tpls in _TEMPLATES.items()
            for t in tpls[:1]  # 每类取 1 条，控制 prompt 长度
        )
        # 最近 3 轮对话上下文
        ctx = ""
        if history:
            ctx = "\n最近对话:\n" + "\n".join(
                f"  {self._clean_text(m.get('role', 'user'))}: {self._clean_text(m.get('content', ''))}"
                for m in history[-3:]
            )

        prompt = f"""你是学习助手的意图识别器。请结合示例和最近对话，判断学生当前最主要的学习意图。

        示例:
        {examples}
        
        {ctx}
        学生消息: "{message}"
        
        意图说明：
        - explain: 希望讲解概念、原理或知识点
        - qa: 针对具体疑问、错误或不理解之处寻求帮助
        - quiz: 希望生成练习题或接受测验
        - review: 希望复习、总结或回顾薄弱点
        - greeting: 普通问候或开始学习
        - other: 无法归类
        
        只返回JSON:
        {{"intent": "<意图值>", "confidence": <0-1>, "reasoning": "<一句话说明>"}}
        
        可选意图: {", ".join(c.value for c in IntentCategory)}"""
        prompt = self._clean_text(prompt)

        try:
            resp = await self.client.messages.create(
                model=self.model,
                max_tokens=256,
                temperature=0.1,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = extract_text_content(resp.content)
            s, e = raw.find("{"), raw.rfind("}") + 1
            data = json.loads(raw[s:e])
            try:
                data["intent"] = IntentCategory(data["intent"])
            except ValueError:
                data["intent"] = IntentCategory.OTHER
            return data
        except Exception as ex:
            logger.warning(f"LLM 识别失败: {ex}")
            return {"intent": IntentCategory.OTHER, "confidence": 0.0, "reasoning": "LLM 失败", "failed": True}

    async def _embedding_recognize(self, message: str) -> Dict[str, Any]:
        """策略 2：Embedding 向量相似度匹配。"""
        #流程：将模板和message全部转化为向量->余弦相似度计算相似度->返回最相似的意图识别类型
        try:
            #将模板全部转换为向量存储再self._tpl_embeddings中
            await self._load_template_embeddings()
            msg_vec = await self._embed_text(message)

            best_cat, best_score = IntentCategory.OTHER, 0.0
            #将message与模板进行余弦相似度计算，得到最高的相似度与其对应的IntentCategory
            for cat, vecs in self._tpl_embeddings.items():
                score = max(_cosine(msg_vec, v) for v in vecs)
                if score > best_score:
                    best_score, best_cat = score, cat

            return {"intent": best_cat, "confidence": best_score}
        except Exception as ex:
            logger.warning(f"Embedding 识别失败: {ex}")
            return {"intent": IntentCategory.OTHER, "confidence": 0.0}

    def _pattern_recognize(self, message: str) -> Dict[str, Any]:
        """关键词规则识别；唯一类别命中时可直接完成路由。"""
        msg = message.lower()
        patterns = {
            IntentCategory.QUIZ: [
                "出题", "考考我", "练习题", "测验", "做题", "quiz",
            ],
            IntentCategory.REVIEW: [
                "复习", "总结", "回顾", "薄弱点", "错题", "review",
            ],
            IntentCategory.QA: [
                "为什么", "哪里错", "怎么改", "看不懂",
                "不理解", "报错", "疑问",
            ],
            IntentCategory.EXPLAIN: [
                "讲一下", "讲讲", "解释", "什么是",
                "原理", "概念", "怎么理解",
            ],
            IntentCategory.GREETING: [
                "你好", "您好", "hello", "hi", "开始学习",
            ],
        }
        matches: List[tuple[IntentCategory, int]] = []
        for category, keywords in patterns.items():
            hits = sum(1 for keyword in keywords if keyword in msg)
            if category == IntentCategory.QUIZ and re.search(
                r"(?:出|来|生成).{0,12}(?:题|练习)", msg
            ):
                hits += 1
            if hits:
                matches.append((category, hits))

        if not matches:
            return {
                "intent": IntentCategory.OTHER,
                "confidence": 0.0,
                "reasoning": "未命中关键词规则",
            }

        matches.sort(key=lambda item: item[1], reverse=True)
        best_cat, best_hits = matches[0]
        # 当关键词匹配大于1 ，有两类Agent的命中都为best_hits
        tied = len(matches) > 1 and matches[1][1] == best_hits

        # 多个类别同分表示问题可能包含复合意图，交给 LLM 结合上下文判断。
        confidence = 0.6 if tied else min(0.98, 0.88 + 0.04 * (best_hits - 1))
        return {
            "intent": best_cat,
            "confidence": confidence,
            "reasoning": (
                "多个意图规则同分，转交 LLM 判断"
                if tied
                else f"关键词规则命中: {best_cat.value}"
            ),
        }

    # ── 投票合并 ──────────────────────────────────────────────────────────────

    def _vote(self, llm: Dict, emb: Dict, pat: Dict) -> IntentCategory:
        """加权投票。embedding 不可用时权重自动转移到 LLM 和 Pattern。"""
        #llm,emb,pat都是IntentCategory+confidence
        if llm.get("failed"):
            if emb.get("intent") != IntentCategory.OTHER and emb.get("confidence", 0.0) > 0:
                return emb["intent"]
            if pat.get("intent") != IntentCategory.OTHER and pat.get("confidence", 0.0) > 0:
                return pat["intent"]
            return IntentCategory.OTHER

        if self._embedding_enabled:
            weights = [(llm, 0.7), (emb, 0.2), (pat, 0.1)]
        else:
            weights = [(llm, 0.85), (pat, 0.15)]
        scores: Dict[IntentCategory, float] = {}
        for result, w in weights:
            cat  = result.get("intent", IntentCategory.OTHER)
            conf = result.get("confidence", 0.0)
            scores[cat] = scores.get(cat, 0.0) + w * conf

        best = max(scores, key=scores.get)  # type: ignore
        return best if scores[best] >= self.threshold else IntentCategory.OTHER

    @staticmethod
    def _result_confidence(
        intent: IntentCategory,
        llm: Dict[str, Any],
        emb: Dict[str, Any],
        pat: Dict[str, Any],
    ) -> float:
        """返回最终命中意图对应的最高来源置信度。"""
        candidates = [
            float(result.get("confidence", 0.0))
            for result in (llm, emb, pat)
            if result.get("intent") == intent
        ]
        return max(candidates, default=0.0)

    # ── 实体提取 ──────────────────────────────────────────────────────────────

    async def _extract_entities(self, message: str) -> Dict[str, List[str]]:
        """用 LLM 从消息中提取结构化实体。"""
        message = self._clean_text(message)
        prompt = f"""从学生消息中提取学习相关的实体。所有字段必须是字符串列表，没有则返回空列表。
        学生消息: "{message}"
        只返回JSON: 
        {{
          "subject": [],
          "course": [],
          "chapter": [],
          "concept": [],
          "difficulty": [],
          "error_type": []
        }}"""
        prompt = self._clean_text(prompt)
        try:
            resp = await self.client.messages.create(
                model=self.model, max_tokens=256, temperature=0.0,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = extract_text_content(resp.content)
            s, e = raw.find("{"), raw.rfind("}") + 1
            return json.loads(raw[s:e])
        except Exception:
            return {
                "subject": [],
                "course": [],
                "chapter": [],
                "concept": [],
                "difficulty": [],
                "error_type": [],
            }

    # ── 辅助 ──────────────────────────────────────────────────────────────────

    async def _load_template_embeddings(self) -> None:
        """懒加载所有模板的 Embedding（只在首次调用时执行）。"""
        missing = [cat for cat in _TEMPLATES if cat not in self._tpl_embeddings]
        if not missing:
            return

        all_texts = [t for cat in missing for t in _TEMPLATES[cat]]
        vecs = [await self._embed_text(text) for text in all_texts]
        idx = 0
        for cat in missing:
            n = len(_TEMPLATES[cat])
            self._tpl_embeddings[cat] = vecs[idx: idx + n]
            idx += n

    async def _embed_text(self, text: str) -> List[float]:
        """
        生成文本向量。

        如果未来接入的官方/兼容客户端提供 embeddings.create，会优先使用远端向量；
        当前 Anthropic SDK 没有该资源时，退化为字符 n-gram 哈希向量。这样不会因为
        Embedding 服务缺失导致三路融合中断。
        """
        embeddings = getattr(self.client, "embeddings", None)
        if embeddings is not None:
            try:
                resp = await embeddings.create(model="voyage-3-lite", input=[text])
                return list(resp.data[0].embedding)
            except Exception as ex:
                logger.warning(f"远端 Embedding 失败，使用本地向量兜底: {ex}")

        return self._local_embedding(text)

    @staticmethod
    def _local_embedding(text: str, dims: int = 256) -> List[float]:
        """稳定的字符 n-gram 哈希向量，用于无远端 Embedding 时的语义近似匹配。"""
        normalized = text.lower().strip()
        vec = [0.0] * dims
        tokens = set()
        for n in (1, 2, 3):
            if len(normalized) >= n:
                tokens.update(normalized[i:i + n] for i in range(len(normalized) - n + 1))
        if not tokens:
            tokens.add(normalized)

        for token in tokens:
            digest = hashlib.md5(token.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:4], "big") % dims
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vec[idx] += sign
        return vec

    def _urgency(self, message: str, intent: IntentCategory) -> UrgencyLevel:
        """学习场景只根据消息中的时间紧迫关键词判断。"""
        msg = message.lower()
        for level, kws in _URGENCY_KEYWORDS.items():
            if any(kw in msg for kw in kws):
                return level
        return UrgencyLevel.LOW

    def _cache_key(self, message: str,
                   history: Optional[List[Dict[str, str]]] = None
                   ) -> str:
        recent = history[-2:] if history else []
        payload = json.dumps(
            {"message": self._clean_text(message), "history": recent},
            ensure_ascii=False,
            sort_keys=True,
        )
        return hashlib.md5(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _clean_text(value: Any) -> str:
        """移除 Unicode 代理字符，避免 HTTP 客户端编码 prompt 时崩溃。"""
        if value is None:
            return ""
        if not isinstance(value, str):
            value = str(value)
        return value.encode("utf-8", errors="ignore").decode("utf-8")

    @property
    def cache_stats(self) -> Dict[str, Any]:
        total = self.cache_hits + self.cache_misses
        return {
            "size": len(self._cache),
            "hits": self.cache_hits,
            "misses": self.cache_misses,
            "hit_rate": self.cache_hits / total if total else 0.0,
        }
