# 模型执行器

`ava.llm_model_executor` 是新的独立模型执行层。

## 结构

- `types.py`：请求、结果、事件等核心类型
- `service.py`：唯一主实现，统一负责请求规范化、provider 调用、同步与流式执行
- `__init__.py`：对外导出正式入口

## 职责

- 接收外层已经组装好的 `instructions + input`
- 规范化为 OpenAI Responses 请求
- 提供同步与流式执行

当前实现不再拆分额外的 request / provider 子模块，避免过度封装。

## 原则

- 不负责业务路由
- 不负责多轮上下文拼接
- 不负责 turn plan 推导
