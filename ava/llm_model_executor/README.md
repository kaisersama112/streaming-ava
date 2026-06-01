# 模型执行器

`ava.llm_model_executor` 是正式的模型执行层。

当前版本统一承载两类执行能力：

- OpenAI Responses 执行
- Agents SDK 执行后端

## 目录

```text
ava/llm_model_executor/
  __init__.py
  types.py
  service.py
  agent_backend.py
```

## 职责

- 接收外层已经组装好的 `instructions + input`
- 规范化为模型请求
- 提供同步与流式执行
- 在需要时切换到 Agents SDK 后端

## 不负责

- 路由决策
- 教育计划求解
- 执行计划构造
- 多轮上下文拼装

## 边界

`inference_runtime` 负责编排，  
`llm_model_executor` 负责真正执行。
