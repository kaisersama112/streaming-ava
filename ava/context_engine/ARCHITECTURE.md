# Context Compiler + LLMService Architecture

## Core Principles
- `ContextCompiler` 只负责编译模型可见上下文
- `LLMService` 只负责构造请求并发送给模型
- responder 使用 `conversation` 维持多轮状态
- `turn_records` 是会话主事实源
- `ConversationState` 不再持有 `history`

## Top-Level Flow

```text
Business Entry
  -> Routing / Reply Orchestration
  -> LLMService
  -> InferenceRequestBuilder
  -> ContextCompiler
  -> OpenAIChatProvider
  -> OpenAI Responses API
```

## Module Layers

### 1. Context Compiler Layer

```text
ava/context_engine/
  __init__.py
  compiler.py
  instructions.py
  skills.py
  memory.py
  continuity.py
  input.py
  types.py
```

#### Main Classes

```text
ContextCompiler
  - ContextSnapshotBuilder
  - RuntimePayloadCompiler
  - MessageCompiler
  - InstructionsCompiler
```

#### Responsibilities
- `build_turn_input()`
  - 规范化原始用户输入
- `build_snapshot()`
  - 生成本轮上下文快照
- `compile_router_envelope()`
  - 生成 router instructions / runtime / messages
- `compile_responder_envelope()`
  - 生成 responder instructions / runtime / messages

## LLM Layer

```text
ava/capabilities/llm/
  service.py
  requests/builder.py
  requests/policy.py
  providers/mapping.py
  providers/openai_chat.py
  streaming/events.py
  types.py
```

#### Main Classes

```text
LLMService
  - InferenceRequestBuilder
  - OpenAIChatProvider
```

#### Responsibilities
- `LLMService.build_context()`
  - 生成标准 `LLMContext`
- `InferenceRequestBuilder.build()`
  - 将 envelope 转换为 `InferenceRequest`
- `OpenAIChatProvider.chat()/stream()`
  - 调用 `responses.create(...)`
  - SDK 不支持时走 HTTP fallback

## Conversation Layer

```text
ava/domain/conversation/state.py
```

#### Main Fields

```text
ConversationState
  - turn_records
  - responder_conversation_id
  - responder_previous_response_id
```

#### Responsibilities
- `turn_records`
  - 保存每轮 user / assistant / decision / strategy / evaluation
- responder conversation state
  - 保存 Responses API 多轮链路标识
- `history`
  - 从 `turn_records` 派生
  - 仅供兼容与调试

## Router vs Responder

### Router Path

```text
TurnInput
  -> ContextCompiler.build_snapshot(profile="router")
  -> compile_router_envelope()
  -> LLMService.route()
```

#### Router Rules
- router 不接入 `conversation`
- router 继续使用压缩后的 `history_messages`
- router 输出的是规划 JSON，不应污染自然对话链

### Responder Path

```text
TurnInput + RouteDecision + TurnPlan
  -> ContextCompiler.build_snapshot(profile="responder_minimal")
  -> compile_responder_envelope()
  -> InferenceRequestBuilder
      -> first turn: seed with compiled history
      -> later turns: current user input only
      -> attach conversation / previous_response_id
  -> LLMService.generate() / stream_generate()
```

#### Responder Rules
- responder 接入 `conversation`
- 首轮迁移时发送编译后的历史作为 seed
- 建链后只发送当前轮输入
- 历史连续性由 Responses API conversation 维持

## Source of Truth

```text
turn_records
  -> snapshot.history_messages
  -> memory summaries
```

#### Meaning
- 现在的真实主事实源是 `turn_records`
- `ConversationState.history` 已完全移除
- memory summary 也改为基于 `turn_records`

## Call Order

### Sync Reply

```text
CLI / app
  -> prepare_state_for_turn()
  -> route_with_context()
  -> build_turn_plan()
  -> generate_reply_sync()
  -> LLMService.build_context(task=GENERATE)
  -> InferenceRequestBuilder.build()
  -> OpenAIChatProvider.chat()
  -> persist_turn()
```

### Streaming Reply

```text
Realtime session
  -> upsert_realtime_user_turn()
  -> route_with_context()
  -> build_turn_plan()
  -> stream_reply_with_callbacks()
  -> LLMService.stream_generate()
  -> OpenAIChatProvider.stream()
  -> complete_realtime_turn()
```

## Class Diagram

```text
ConversationState
  - turn_records
  - responder_conversation_id
  - responder_previous_response_id

ContextCompiler
  - ContextSnapshotBuilder
  - RuntimePayloadCompiler
  - MessageCompiler
  - InstructionsCompiler

LLMService
  - InferenceRequestBuilder
  - OpenAIChatProvider

InferenceRequestBuilder
  -> CompiledContextEnvelope
  -> InferenceRequest

OpenAIChatProvider
  -> Responses API
```

## Current Invariants
- 根包 `ava.context_engine` 只暴露 `ContextCompiler`
- `LLMService` 是唯一模型发送主入口
- router 与 responder 必须分离上下文策略
- `turn_records` 优先于 `history`
- skills 必须来自 `prompt-plugin/plugins`
