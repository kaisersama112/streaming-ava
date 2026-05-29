# LLM Capability

`ava.capabilities.llm` 现在只负责一件事：  
把外层已经准备好的 `instructions + messages` 发送给 OpenAI Responses API。

---

## 当前结构

```text
ava/capabilities/llm/
  __init__.py
  service.py
  request.py
  provider.py
  types.py
```

---

## 模块职责

### `service.py`

- `RequestContextBuilder`
- `LLMService`

职责：
- 为 router / responder 构建 `ModelRequestContext`
- 协调上下文构建、请求构建、provider 调用

### `request.py`

- `RequestPolicy`
- `InferenceRequestBuilder`

职责：
- 解析 `model / timeout / temperature`
- 把 `ModelRequestContext` 转成 `InferenceRequest`
- 组装 Responses API 所需的 `instructions` 和 `input`

### `provider.py`

职责：
- 纯执行层
- 调用 OpenAI SDK Responses API
- 处理同步 / 流式输出

### `types.py`

包含：
- `InferenceTask`
- `ModelRequestContext`
- `InferenceRequest`
- `InferenceResult`
- `InferenceEvent`
- `OutputTextDelta`
- `InferenceCompleted`
- `InferenceError`
- `LLMProvider`

---

## 请求主链路

```text
ConversationContext
  -> instructions
  -> messages
  -> ModelRequestContext
  -> InferenceRequest
  -> OpenAIResponsesProvider
```

---

## 设计原则

- 模型请求围绕 `instructions + messages`
- `request.py` 不负责业务上下文推理
- `provider.py` 不负责 prompt / context 组装
- 不使用 `previous_response_id` 作为主链路
- 每轮都显式传本轮 `instructions` 和完整 `messages`
