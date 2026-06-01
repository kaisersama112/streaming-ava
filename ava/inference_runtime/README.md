# 推理运行时

`ava.inference_runtime` 是正式的独立推理编排层。

当前版本已经收缩为纯运行时，不再承载：

- 教育计划建模
- 教育计划归一化
- 策略构造
- Agents SDK 执行后端

这些职责已经迁回其它正式模块。

## 目录

```text
ava/inference_runtime/
  __init__.py
  types.py
  service.py
```

## 职责

- 接收外部已构建好的 `TurnPlan`
- 以 `PromptPackage + payload` 作为正式执行输入
- 选择回复执行路径
- 触发最终回复生成

## `TurnPlan` 结构

- `decision`
  - 当前轮正式路由结果，类型为 `RouteDecision`
- `strategy`
  - 上游保留下来的内部策略对象，类型为 `BranchStrategy | None`
  - 仅供调试与上游衔接，不是运行时正式依赖
- `prompt_package`
  - 当前轮正式 Prompt 组合结果
  - 类型为 `PromptPackage | None`
  - 这是运行时读取 Prompt 语义的唯一正式入口
- `payload`
  - 最终模型请求载荷
  - 包含：
    - `instructions`
    - `input`
- `execution`
  - 运行控制信息
  - 包含：
    - `orchestrator_name`
    - `model`
- `runtime_context`
  - 运行时附带对象
  - 当前包含：
    - `conversation_context`
- `debug`
  - 调试与追踪信息
  - 当前包含：
    - `router_plan`
    - `active_skills`
    - `prompt_package`

## 不负责

- 路由决策
- Prompt/策略选择
- `TurnPlan` 构建
- 教育域计划求解
- 底层模型协议细节
- Agent 后端实现

## 依赖关系

```text
router_selector
  -> 提供 RouteDecision / strategy builder / education resolver

inference_runtime
  -> 消费 TurnPlan
  -> 调用 llm_model_executor
```
