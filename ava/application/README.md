# Application Layer

`ava/application/` 负责把一次用户输入真正执行成一个完整 turn。

它不定义底层外部系统协议，也不承载长期状态模型；它做的是：

- 组织调用顺序
- 串起 `domain` 与 `infrastructure`
- 决定何时路由、何时编排、何时持久化、何时做 speech postprocess

## 边界

这一层负责：

- turn 前准备与 turn 后持久化
- Router 调用与 fallback 编排
- TurnPlan 构建
- realtime session 控制
- speech postprocess 接入点
- trace/evaluation 写入

这一层不负责：

- 定义 `ConversationState`、`ContextSnapshot`、`RouteDecision` 这类领域模型
- 直接实现 OpenAI / TTS / ASR / FastRTC SDK 适配
- 保存 Prompt 资产本体

## 当前子模块

- `conversation.py`
  - 会话状态加载、prepare、persist
- `factories.py`
  - PromptCenter / Router 构造
- `multimodal.py`
  - `AttachmentPayload -> TurnInput`
- `routing/`
  - Router 请求组装、LLM 调用、JSON 解析、fallback
- `orchestration/`
  - `RouteDecision -> TurnPlan`
- `realtime/`
  - 全双工 session、barge-in、turn lifecycle
- `services/`
  - 面向入口的应用服务
- `speech/`
  - 数学公式口播后处理
- `voice_stream.py`
  - token 到流式 TTS 的低延迟提交管线
- `trace.py`
  - 结构化追踪日志

## 常见调用链

### 单轮服务

```text
build_turn_input
-> prepare_state_for_turn
-> router.route
-> build_turn_plan
-> llm_client.chat / chat_stream
-> build_speech_text
-> persist_turn
```

### Realtime

```text
ASR partial/final / text submit
-> RealtimeConversationSession
-> submit_turn
-> router.route
-> build_turn_plan
-> llm stream
-> LatexAwareSpeechBuffer
-> StreamingVoicePipeline
-> complete_realtime_turn
```

## 与相邻层关系

- 读取和写入的核心领域对象来自 [ava/domain/README.md](/app/streaming-ava/ava/domain/README.md)
- 依赖的外部系统适配来自 [ava/infrastructure/README.md](/app/streaming-ava/ava/infrastructure/README.md)
- 更细的子系统说明见：
  - [orchestration/README.md](/app/streaming-ava/ava/application/orchestration/README.md)
  - [realtime/README.md](/app/streaming-ava/ava/application/realtime/README.md)
  - [routing/README.md](/app/streaming-ava/ava/application/routing/README.md)
  - [services/README.md](/app/streaming-ava/ava/application/services/README.md)
  - [speech/README.md](/app/streaming-ava/ava/application/speech/README.md)
