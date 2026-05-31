# LLM Capability

`ava.capabilities.llm` 现在只负责一件事：  
把外层已经准备好的 `instructions + messages` 发送给 OpenAI Responses API。

---

## 当前结构

```text
ava/capabilities/llm/
  __init__.py
  types.py
```

---

## 模块职责

### 薄转发层

职责：
- 这里只保留旧导入路径
- 真实实现统一转发到 `ava.llm_model_executor`

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
  -> LLMService
```

---

## 设计原则

- 模型请求围绕 `instructions + messages`
- `request.py` 不负责业务上下文推理
- `provider.py` 不负责 prompt / context 组装
- 不使用 `previous_response_id` 作为主链路
- 每轮都显式传本轮 `instructions` 和完整 `messages`
