# 路由选择模块

`ava.router_selector` 是新的独立路由实现层。

## 结构

- `schema.py`：路由决策数据结构
- `service.py`：唯一主实现，统一负责请求装配、模型调用、结果治理
- `__init__.py`：对外导出正式入口

## 职责

- 根据当前轮上下文构造路由请求
- 调用路由模型
- 解析模型输出并生成 `RouteDecision`
- 输出当前轮的 `router_plan`

当前实现不再拆分额外的 request / policy 子模块，避免过度封装。

## 输入

- `ConversationContext`
- 标准 `user message`
- 当前轮模型配置

## 输出

- `RouteDecision`
- `router_plan`
- 原始 request / response 调试信息

## 边界

- 不负责完整多轮上下文构造
- 不负责最终回复生成
- 不负责底层 OpenAI SDK 细节
