"""
亮点：多 Agent 路由与编排

核心问题：多 Agent 情况下如何做 Routing？

路由策略（三层决策）：
  1. 意图路由 —— 根据 IntentCategory 直接映射到专属 Agent
  2. 性能路由 —— 同类 Agent 有多个时，选成功率最高、延迟最低的
  3. 降级路由 —— 专属 Agent 不可用时，自动降级到 GeneralAgent

并行协作：
  - 复杂问题（如"技术问题 + 账单问题"）可同时派发给多个 Agent
  - 结果由 Orchestrator 合并后返回

升级机制：
  - Agent 置信度低于阈值 → 自动升级到更高级 Agent 或转人工
"""
import asyncio
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Dict, List, Optional

from anthropic import AsyncAnthropic

from core.intent_recognizer import IntentCategory, IntentRecognizer, UrgencyLevel
from core.llm_utils import extract_text_content

logger = logging.getLogger(__name__)


# ── 数据结构 ──────────────────────────────────────────────────────────────────

class AgentType(Enum):
    EXPLAIN   = "explain"    # 讲解Agent
    QA = "qa"  # 答疑Agent
    QUIZ   = "quiz"    # 出题Agent

@dataclass
class AgentStats:
    """Agent 运行时统计，供 Monitor 和路由决策使用。"""
    total:     int   = 0
    success:   int   = 0
    total_ms:  float = 0.0
    monitor_penalty: float = 0.0

    @property
    def success_rate(self) -> float:
        return self.success / self.total if self.total else 1.0

    @property
    def avg_ms(self) -> float:
        return self.total_ms / self.total if self.total else 0.0

    def routing_score(self) -> float:
        """路由评分：成功率高、延迟低的 Agent 得分高。"""
        latency_score = 1.0 / (1.0 + self.avg_ms / 1000)
        base_score = self.success_rate * 0.7 + latency_score * 0.3
        return base_score * max(0.0, 1.0 - self.monitor_penalty)


@dataclass
class AgentResponse:
    agent_type:  AgentType
    content:     str
    success:     bool
    confidence:  float = 1.0
    latency_ms:  float = 0.0
    escalate:    bool  = False   # 是否需要升级


@dataclass
class Request:
    message:     str
    user_id:     str
    conv_id:     str
    context:     str = ""        # 来自 MemoryManager 的格式化上下文
    history:     Optional[List[Dict[str, str]]] = None  # 对话历史，传给意图识别
    intent:      Optional[IntentCategory] = None
    urgency:     Optional[UrgencyLevel]   = None
    request_id:  str = field(default_factory=lambda: str(uuid.uuid4())[:8])


@dataclass
class OrchestratorResult:
    request_id:  str
    response:    str
    agent_type:  AgentType
    intent:      Optional[IntentCategory]
    success: bool = True
    escalated:   bool  = False
    latency_ms:  float = 0.0


# ── 基础 Agent ────────────────────────────────────────────────────────────────

class BaseAgent:
    """所有 Agent 的基类，封装 LLM 调用和统计。"""

    agent_type: AgentType
    system_prompt: str

    def __init__(self, client: AsyncAnthropic, model: str, skill_manager: Optional[Any] = None):
        self._client = client
        self._model  = model
        self._skill_manager = skill_manager
        self.stats   = AgentStats()

    async def handle(self, req: Request) -> AgentResponse:
        start_time = time.monotonic()
        succeeded = False
        content = ""
        try:
            content = await self._call_llm(req)
            succeeded = True
        except Exception as ex:
            logger.exception("%s 处理失败", self.agent_type.value)
            content = "抱歉，处理您的请求时出现问题，请稍后重试。"
        finally:
            ms = (time.monotonic() - start_time) * 1000
            self.stats.total += 1
            self.stats.total_ms += ms
            if succeeded:
                self.stats.success += 1
            escalate = self._needs_escalation(content)
        return AgentResponse(
            agent_type=self.agent_type,
            content=content,
            success=succeeded,
            latency_ms=ms,
            escalate=escalate,
            )

    async def _call_llm(self, req: Request) -> str:
        resp = await self._client.messages.create(**self._llm_request(req))
        content = extract_text_content(resp.content).strip()

        #进一步对content进行检验
        if not content:
            block_types = [
                getattr(block, "type", type(block).__name__)
                for block in (resp.content or [])
            ]

            logger.error(
                "LLM 返回空回答: stop_reason=%s, blocks=%s",
                getattr(resp, "stop_reason", None),
                block_types,
            )
            raise RuntimeError("LLM 返回了空回答")

        return content

    def _llm_request(self, req: Request) -> Dict[str, Any]:
        """统一构建普通调用和流式调用使用的模型参数。"""
        def _clean(s: str) -> str:
            return s.encode("utf-8", errors="ignore").decode("utf-8")

        messages = []
        if req.context:
            messages.append({"role": "user", "content": f"[背景信息]\n{_clean(req.context)}"})
            messages.append({"role": "assistant", "content": "好的，我已了解背景信息。"})
        messages.append({"role": "user", "content": _clean(req.message)})

        return {
            "model": self._model,
            "max_tokens": int(os.getenv("AGENT_MAX_TOKENS", "4096")),
            "system": self._build_system_prompt(req),
            "messages": messages,
        }

    async def stream(self, req: Request) -> AsyncIterator[str]:
        """直接转发模型文本增量，并与普通调用共用 Agent 统计口径。"""
        start_time = time.monotonic()
        succeeded = False
        chunks: List[str] = []
        try:
            async with self._client.messages.stream(**self._llm_request(req)) as response_stream:
                async for text in response_stream.text_stream:
                    if text:
                        chunks.append(text)
                        yield text

            if not "".join(chunks).strip():
                raise RuntimeError("LLM 返回了空回答")
            succeeded = True
        finally:
            ms = (time.monotonic() - start_time) * 1000
            self.stats.total += 1
            self.stats.total_ms += ms
            if succeeded:
                self.stats.success += 1

    def _build_system_prompt(self, req: Request) -> str:
        """把动态加载的 Skills 拼入 system prompt，让业务规则随请求生效。"""
        if self._skill_manager is None:
            return self.system_prompt
        skill_prompt = self._skill_manager.prompt_for(req.message, self.agent_type.value)
        if not skill_prompt:
            return self.system_prompt
        return f"{self.system_prompt}\n\n[动态 Skills]\n{skill_prompt}"

    def _needs_escalation(self, content: str) -> bool:
        """检测回答是否建议教师介入。"""
        keywords = [
            "建议咨询老师",
            "需要教师确认",
            "请老师进一步指导",
            "需要人工辅导",
        ]
        return any(keyword in content for keyword in keywords)


class ExplainAgent(BaseAgent):
    agent_type    = AgentType.EXPLAIN
    system_prompt = (
        "你是学习讲解 Agent。"
        "根据学生当前学习进度和薄弱点讲解知识。"
        "优先依据提供的课程资料，不要编造课程内容。"
        "先解释核心概念，再给一个简单示例，最后用一个小问题检查理解。"
        "控制一次回复的新知识数量，避免使用学生尚未学习的高级概念。"
    )


class QaAgent(BaseAgent):
    agent_type    = AgentType.QA
    system_prompt = (
        "你是学习答疑 Agent。"
        "先判断学生具体卡在哪一步，再进行针对性解释。"
        "如果学生正在完成练习，优先给提示、思路和检查方向，"
        "不要立即给出完整答案。"
        "如果信息不足，先提出一个最关键的澄清问题。"
        "优先依据课程资料回答，并明确区分资料内容和补充解释。"
    )


class QuizAgent(BaseAgent):
    agent_type    = AgentType.QUIZ
    system_prompt = (
        "你是练习出题 Agent。"
        "根据学生已学内容和薄弱点生成一道难度适中的题目。"
        "题目必须注明考查知识点和难度。"
        "默认只输出题目，不同时泄露答案。"
        "只有学生提交答案或明确要求答案后，才进行评分和讲解。"
    )


# ── 编排器 ────────────────────────────────────────────────────────────────────

class AgentOrchestrator:
    """
    多 Agent 编排器。

    路由逻辑（三层）：
      1. 意图 → Agent 类型映射
      2. 同类多实例时按 routing_score() 选最优
      3. 专属 Agent 失败时降级到 GeneralAgent
    """

    # 意图 → Agent 类型的静态映射（路由表）
    _INTENT_ROUTING: Dict[IntentCategory, AgentType] = {
        IntentCategory.EXPLAIN:  AgentType.EXPLAIN,
        IntentCategory.QA:    AgentType.QA,
        IntentCategory.QUIZ:    AgentType.QUIZ,
        IntentCategory.REVIEW: AgentType.EXPLAIN,
        IntentCategory.GREETING: AgentType.EXPLAIN
        # 其余意图 → GENERAL（默认）
    }

    def __init__(
        self,
        api_key:  str,
        base_url: Optional[str] = None,
        model:    str = "claude-3-5-sonnet-20241022",
        skill_manager: Optional[Any] = None,
    ):
        kwargs: Dict[str, Any] = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        client = AsyncAnthropic(**kwargs)

        self._intent_recognizer = IntentRecognizer(api_key=api_key, base_url=base_url, model=model)
        self._skill_manager = skill_manager

        # Agent 池：每种类型可有多个实例（水平扩展）
        self._pool: Dict[AgentType, List[BaseAgent]] = {
            AgentType.EXPLAIN:   [ExplainAgent(client, model, skill_manager)],
            AgentType.QA: [QaAgent(client, model, skill_manager)],
            AgentType.QUIZ:   [QuizAgent(client, model, skill_manager)],
        }

    def set_skill_manager(self, skill_manager: Optional[Any]) -> None:
        """更新 SkillManager 引用，供运行时重载或测试替换使用。"""
        self._skill_manager = skill_manager
        for agents in self._pool.values():
            for agent in agents:
                agent._skill_manager = skill_manager

    # ── 主入口 ────────────────────────────────────────────────────────────────

    async def run(self, req: Request) -> OrchestratorResult:
        """
        处理一次请求的完整流程：
          意图识别 → 路由选 Agent → 执行 → 检查升级 → 返回结果
        """
        t0 = time.monotonic()

        # 1. 意图识别（如果调用方已识别则跳过）
        if req.intent is None:
            intent_result = await self._intent_recognizer.recognize(req.message, history=req.history)
            req.intent  = intent_result.intent
            req.urgency = intent_result.urgency

        # 复杂问题自动并行协作，例如同一句同时涉及登录故障和扣款/退款。
        collaboration = self._collaboration_targets(req)
        if len(collaboration) > 1:
            return await self.run_parallel(req, collaboration)

        # 2. 路由：选择 Agent 类型
        agent_type = self._route(req.intent, req.urgency)

        # 3. 执行（含降级）
        response = await self._execute(req, agent_type)

        # 4. 升级检查
        escalated = response.escalate or req.urgency == UrgencyLevel.CRITICAL
        if escalated:
            logger.warning("学习请求 %s 建议人工关注: urgency=%s",req.request_id,req.urgency,)
            # 生产环境：此处创建工单、通知人工客服

        return OrchestratorResult(
            request_id=req.request_id,
            response=response.content,
            agent_type=response.agent_type,
            intent=req.intent,
            # 用于判断该编排结果是否成功
            success=response.success,
            escalated=escalated,
            latency_ms=(time.monotonic() - t0) * 1000,
        )

    async def run_parallel(self, req: Request, agent_types: List[AgentType]) -> OrchestratorResult:
        """
        并行派发给多个 Agent，合并结果。
        适用于复杂问题（如同时涉及技术和账单）。
        """
        t0 = time.monotonic()
        tasks = [self._execute(req, at) for at in agent_types]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        # 合并：拼接所有成功响应
        successful_responses = [
            response
            for response in responses
            if isinstance(response, AgentResponse) and response.success
        ]

        parts = [
            f"[{response.agent_type.value}]\n{response.content}"
            for response in successful_responses
        ]

        combined = "\n\n".join(parts) if parts else "抱歉，所有 Agent 均处理失败。"
        escalated = any(isinstance(r, AgentResponse) and r.escalate for r in responses)

        return OrchestratorResult(
            request_id=req.request_id,
            response=combined,
            agent_type=agent_types[0],
            intent=req.intent,
            #用于判断该编排结果是否成功
            success=bool(successful_responses),
            escalated=escalated,
            latency_ms=(time.monotonic() - t0) * 1000,
        )

    async def stream(self, req: Request) -> AsyncIterator[Dict[str, Any]]:
        """
        流式执行一次请求。

        单 Agent 直接转发模型 token；复合意图继续使用原并行编排，完成后作为
        一个 delta 返回，避免多个 Agent 的 token 相互穿插破坏可读性。
        """
        t0 = time.monotonic()
        if req.intent is None:
            intent_result = await self._intent_recognizer.recognize(
                req.message, history=req.history
            )
            req.intent = intent_result.intent
            req.urgency = intent_result.urgency

        collaboration = self._collaboration_targets(req)
        if len(collaboration) > 1:
            yield {
                "type": "meta",
                "intent": req.intent.value if req.intent else "other",
                "agent_type": collaboration[0].value,
            }
            result = await self.run_parallel(req, collaboration)
            yield {"type": "delta", "text": result.response}
            yield {"type": "done", "result": result}
            return

        requested_type = self._route(req.intent, req.urgency)
        agent = self._best_agent(requested_type)
        if agent is None:
            agent = self._best_agent(AgentType.EXPLAIN)
        if agent is None:
            raise RuntimeError("学习服务暂时不可用，请稍后重试")

        yield {
            "type": "meta",
            "intent": req.intent.value if req.intent else "other",
            "agent_type": agent.agent_type.value,
        }

        chunks: List[str] = []
        try:
            async for text in agent.stream(req):
                chunks.append(text)
                yield {"type": "delta", "text": text}
        except Exception:
            # 尚未向客户端输出正文时，保留原来的专属 Agent 降级语义。
            if chunks or requested_type == AgentType.EXPLAIN:
                raise
            logger.warning("%s 流式处理失败，降级到 ExplainAgent", requested_type.value)
            fallback = self._best_agent(AgentType.EXPLAIN)
            if fallback is None or fallback is agent:
                raise
            agent = fallback
            async for text in agent.stream(req):
                chunks.append(text)
                yield {"type": "delta", "text": text}

        content = "".join(chunks).strip()
        if not content:
            raise RuntimeError("LLM 返回了空回答")

        escalated = (
            agent._needs_escalation(content)
            or req.urgency == UrgencyLevel.CRITICAL
        )
        result = OrchestratorResult(
            request_id=req.request_id,
            response=content,
            agent_type=agent.agent_type,
            intent=req.intent,
            success=True,
            escalated=escalated,
            latency_ms=(time.monotonic() - t0) * 1000,
        )
        yield {"type": "done", "result": result}

    # ── 路由逻辑 ──────────────────────────────────────────────────────────────

    def _route(self, intent: Optional[IntentCategory], urgency: Optional[UrgencyLevel]) -> AgentType:
        """
        根据学习意图选择 Agent。
        """
        if urgency == UrgencyLevel.CRITICAL:
            return AgentType.EXPLAIN

        if intent and intent in self._INTENT_ROUTING:
            target = self._INTENT_ROUTING[intent]
            # 如果目标类型有可用实例则使用，否则降级
            if target in self._pool and self._pool[target]:
                return target

        return AgentType.EXPLAIN

    def _collaboration_targets(self, req: Request) -> List[AgentType]:
        """
        判断是否需要多个 Agent 并行协作。
        意图识别通常只返回一个主意图；这里用领域关键词补充检测复合问题，
        """
        msg = req.message.lower()
        targets: List[AgentType] = []

        explain_keywords = [
            "解释", "讲一下", "什么是", "原理", "概念",
        ]
        qa_keywords = [
            "为什么", "哪里错", "不理解", "怎么改", "报错",
        ]
        quiz_keywords = [
            "出题", "练习", "考考我", "测验",
        ]

        if (req.intent == IntentCategory.EXPLAIN or
            any(keyword in msg for keyword in explain_keywords)
        ):
            targets.append(AgentType.EXPLAIN)

        if (req.intent == IntentCategory.QA
            or any(keyword in msg for keyword in qa_keywords)
        ):
            targets.append(AgentType.QA)

        if (req.intent == IntentCategory.QUIZ
            or any(keyword in msg for keyword in quiz_keywords)
        ):
            targets.append(AgentType.QUIZ)

        # 保持顺序去重，并只返回当前有实例的 Agent 类型。
        deduped = list(dict.fromkeys(targets))
        return [agent_type for agent_type in deduped if self._pool.get(agent_type)]

    def _best_agent(self, agent_type: AgentType) -> Optional[BaseAgent]:
        """
        性能路由：从同类 Agent 中选 routing_score() 最高的。
        这是"基于在线表现动态调整路由"的核心。

        优先选择健康 Agent。
        如果该类型只有一个实例，或者所有实例都被 Monitor 降权，
        仍返回评分最高的实例；是否真正不可用应由实际执行结果决定。
        """
        agents = self._pool.get(agent_type, [])
        if not agents:
            return None
        healthy = [
            agent for agent in agents
            if agent.stats.monitor_penalty < 0.7
        ]
        candidate = healthy if healthy else agents

        return max(candidate, key=lambda a: a.stats.routing_score())

    async def _execute(self, req: Request, agent_type: AgentType) -> AgentResponse:
        """执行 Agent，失败时降级到 ExplainAgent。"""
        agent = self._best_agent(agent_type)
        if agent is None:
            agent = self._best_agent(AgentType.EXPLAIN)
        if agent is None:
            return AgentResponse(
                agent_type=AgentType.EXPLAIN,
                content="学习服务暂时不可用，请稍后重试",
                success=False,
            )

        response = await agent.handle(req)

        # 专属 Agent 失败时降级到 ExplainAgent
        if not response.success and agent_type != AgentType.EXPLAIN:
            logger.warning(f"{agent_type.value} 失败，降级到 ExplainAgent")
            fallback = self._best_agent(AgentType.EXPLAIN)
            if fallback:
                response = await fallback.handle(req)

        return response

    # ── 统计（供 Monitor 读取）────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        result = {}
        for agent_type, agents in self._pool.items():
            for i, agent in enumerate(agents):
                key = f"{agent_type.value}_{i}"
                result[key] = {
                    "total":        agent.stats.total,
                    "success_rate": round(agent.stats.success_rate, 3),
                    "avg_ms":       round(agent.stats.avg_ms, 1),
                    "monitor_penalty": round(agent.stats.monitor_penalty, 3),
                    "routing_score": round(agent.stats.routing_score(), 3),
                }
        return result

    def update_routing_penalties(self, penalties: Dict[str, float]) -> None:
        """
        接收 Monitor 的在线表现反馈，动态调整路由惩罚项。

        penalties 的 key 使用 get_stats() 中的 agent key，例如 technical_0。
        """
        for agent_type, agents in self._pool.items():
            for i, agent in enumerate(agents):
                key = f"{agent_type.value}_{i}"
                penalty = penalties.get(key, 0.0)
                agent.stats.monitor_penalty = min(max(penalty, 0.0), 0.9)
