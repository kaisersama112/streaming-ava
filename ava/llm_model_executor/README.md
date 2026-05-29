# 模型执行器

`ava.llm_model_executor` 是当前系统唯一的模型执行实现层。

## 职责
- 封装openai sdk 统一调用 OpenAI Responses API
- 对外提供 统一的同步 / 流式输出

## 原则

- 不负责业务路由
- 不负责多轮上下文拼接
- 不负责 turn plan 或 reply 编排
