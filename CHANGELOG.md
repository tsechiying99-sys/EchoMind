# 修改日志

## 2026-08-22

### 前端流式输出

- 聊天页优先请求 `POST /chat/stream`，使用 `fetch + ReadableStream + TextDecoder` 持续解析 SSE 数据。
- 支持 `delta`、`token`、`meta`、`done`、`error` 事件，以及 `data: [DONE]` 结束标记。
- 收到文本增量时立即更新同一条助手消息，并显示闪烁光标、自动滚动和输出模式提示。
- 后端未提供流式接口（404、405、501）时，自动回退现有 `POST /chat`，并渐进显示完整回答，保证原接口仍可使用。
- 取消操作同时支持中止 SSE 请求、普通 Axios 请求和兼容模式的渐进展示。
- 空回答不会作为成功消息保留；等待动画只在首个文本片段到达前显示。

### 后端 SSE 流式接口

- 新增 `POST /chat/stream`，响应类型为 `text/event-stream`，与前端已经实现的流式客户端直接匹配。
- 新增 `meta`、`delta`、`done`、`error` 四类 SSE 事件；中文数据使用 UTF-8 JSON 传输。
- Agent 使用 Anthropic SDK 的 `messages.stream()` 直接转发模型文本增量，不再等待完整回答后才返回。
- 普通调用和流式调用共用模型参数、System Prompt、动态 Skills、Memory 与 RAG 上下文。
- `/chat` 和 `/chat/stream` 共用请求准备函数；Memory 与 RAG 仍保持并行读取。
- 单 Agent 请求真正逐 token 输出；复合意图保持原有多 Agent 并行合并逻辑，合并完成后作为一个增量发送，避免多个回答相互穿插。
- 流式生成成功后写入用户消息、助手回答并异步更新学习画像；客户端中断时取消上游生成，不写入不完整回答。
- 回答已经输出但记忆写入失败时只记录服务端错误，不把有效回答改判为失败。
- 保留原有 `POST /chat`，旧客户端与 PowerShell 测试命令不受影响。

### 流式接口验证

- `api/main.py`、`agents/agent_orchestrator.py` 及项目 Python 文件语法检查通过。
- `git diff --check` 未发现本次流式接口新增代码的空白错误；输出中的既有提示来自此前修改的其他文件。
- 前端生产构建通过，可识别后端 SSE 响应并显示“实时流式输出”。

### 流式输出卡顿修复

- 修复 Vue 响应式对象使用错误：助手占位消息现在从响应式数组中重新获取，SSE 文本到达时会立即触发页面更新。
- 聊天主链路的 RAG 默认改为一次向量检索，不再为每条消息额外调用 LLM 做查询改写和结果重排。
- `/search` 等检索接口保留原有增强检索能力；设置 `CHAT_RAG_MODE=enhanced` 也可以恢复聊天链路的查询改写和重排。
- 增加“流式首段已发送”和“流式回答完成”日志，记录耗时，便于区分前置检索慢、模型首字慢和前端显示问题。
- 根据 2026-08-22 15:47 的日志，原请求约 12.2 秒用于增强 RAG，Agent 完整生成约 24.7 秒；后端实际上已经完成回答并更新画像，未显示回答的直接原因是前端没有响应式刷新。

本次修改针对 `/chat` 同步链路减少不必要的等待，不引入 LangGraph。

### 1. 意图识别改为规则优先、LLM 兜底

- 明确命中单一学习意图关键词时直接返回规则结果，不再调用 LLM。
- 增加“出/来/生成……题或练习”的短句规则，覆盖“给我出一道函数参数的题”等非连续关键词表达。
- 调整规则置信度算法，单一类别命中时置信度从原来的低比例分数改为至少 `0.88`。
- 多个意图类别命中数相同时视为模糊输入，继续使用 LLM 和轻量 Embedding 判断。
- 最终置信度改为取命中意图对应来源的最高置信度。

### 2. 暂停独立实体提取

- `recognize()` 不再调用 `_extract_entities()`，避免每轮对话额外产生一次 LLM 请求。
- `IntentResult.entities` 暂时返回空字典，保留原实体提取方法供后续需要时恢复。

### 3. Memory 与 RAG 并行读取

- `/chat` 使用 `asyncio.create_task()` 同时启动 Memory 上下文读取和课程资料检索。
- 使用 `asyncio.gather()` 合并两个结果，然后构建 Agent 上下文。
- 保持原有接口请求体和响应体不变，Vue 前端不需要同步修改。

### 预期效果

- 讲解、答疑、出题等明确问题减少意图识别 LLM 调用。
- 所有聊天请求暂停实体提取 LLM 调用。
- Memory 与 RAG 的前置耗时由串行累加改为取两者较慢值。

### 验证结果

- “给我讲一下 Python 函数”“为什么这个变量访问不到？”“给我出一道函数参数的题”均由规则正确识别，置信度为 `0.88`，LLM 调用数为 `0`。
- 同分复合意图进入 LLM 兜底，LLM 调用数为 `1`。
- 实体提取调用数为 `0`，`IntentResult.entities` 返回空字典。
- Memory 与 RAG 各模拟耗时 `0.2s` 时，预热后的 `/chat` 前置阶段总耗时约 `0.201s`；若串行执行应约为 `0.4s`。
- 项目 Python 文件语法检查通过。

## 2026-08-19

本次修改围绕 EchoMind 学习助手的 RAG 主链路、长期学习画像、LLM 空回答处理和默认多轮评测数据展开。未新增 `learning_level` 字段。

### 1. 修复 RAG 主链路

- 在 `api/main.py` 的 `_should_use_knowledge()` 中为非空、非寒暄消息补充 `return True`，避免 `/chat` 永远跳过课程资料检索。
- 构建知识库上下文时跳过 fallback 结果，避免把降级提示误标记为有效知识。
- 根据文档标题和内容对多路检索结果去重，并限制最终注入的片段数量。
- 更新 RAG 提示，要求 Agent 优先依据课程资料，并在资料不足时区分课程内容与通用知识。

### 2. 调整长期薄弱点画像存储

- 在 `core/llm_utils.py` 中增加 `extract_json_value()`，用于从 LLM 输出中提取合法 JSON。
- 用户画像文档 ID 从“用户 + 会话”调整为稳定的用户级 ID：`{user_id}_profile`。
- 将 ChromaDB 的“先删除再新增”改为 `upsert()`，支持覆盖更新同一用户画像。
- 读取画像时按稳定文档 ID 查询，不再使用 `where + limit=1` 获取不确定记录。
- 画像字段保持为：
  - `learning_progress`
  - `weak_points`
  - `recent_mistakes`
  - `preferred_style`
- 本次未新增 `learning_level` 字段。

### 3. 防止空回答被记录为成功

- Agent 从 LLM 响应中提取文本后执行 `strip()` 和非空检查。
- 当 LLM 返回空内容时，记录 `stop_reason` 和内容块类型，并抛出异常进入失败处理。
- 空回答不再增加 Agent 成功次数，而是返回统一的失败提示。
- Agent 回答的 `max_tokens` 从 1024 调整为 2048，降低模型在生成正文前耗尽 token 的概率。

### 4. 修复默认多轮评测数据解析

- `EndToEndEvaluator._dialog_turns()` 现在同时支持字符串 turn 和字典 turn。
- 字典 turn 会读取 `message` 字段，不再把整个 Python 字典转换成字符串后发送给 Agent。
- 默认意图和对话用例已替换为讲解、答疑、出题、复习和寒暄等学习场景。

### 验证结果

- `GET /health`：通过。
- “给我讲一下 Python 函数”：路由到 `explain` Agent，回答非空，`knowledge_used=true`。
- “为什么这个变量访问不到？”：路由到 `qa` Agent，回答非空，`knowledge_used=true`。
- “给我出一道函数参数的题”：路由到 `quiz` Agent，回答非空，`knowledge_used=true`。
- 空 LLM 响应模拟测试：通过；结果被标记为失败，Agent 成功计数不增加。
- 默认多轮评测解析测试：通过；两个默认用例均被解析为正常的问题字符串列表。
- 固定画像 ID 与 ChromaDB `upsert`：写入链路通过。
- 薄弱点内容提取：未通过。DeepSeek 在画像更新调用中仍可能返回空内容，当前测试画像仍为四个空数组。

### 当前已知问题

- DeepSeek 的查询改写、意图识别和画像提取偶尔返回空文本或非 JSON 内容；系统能降级，但会影响画像更新和额外增加延迟。
- 当前端到端请求耗时约 29～48 秒，RAG 查询改写、意图识别、Agent 回答和画像更新包含多次 LLM 调用。
- `AgentType` 已移除 `ESCALATION`，但紧急路由仍引用 `AgentType.ESCALATION`；命中 CRITICAL 紧急度时可能抛出 `AttributeError`。
- ChromaDB telemetry 仍会输出 PostHog 参数不兼容错误，但不影响当前检索请求返回。
- 性能监控阈值仍为 3000ms，与当前模型的实际响应时间不匹配，会产生重复延迟告警。
