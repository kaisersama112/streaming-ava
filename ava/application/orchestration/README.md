# Orchestration

`ava/application/orchestration/` 负责把 Router 返回的：

- `RouteDecision`
- `router_plan`

落成真正可执行的：

- `BranchStrategy`
- responder `messages`
- `TurnPlan`

这里已经不再做第二轮语义识别。它当前做的是“模型规划结果物化”，不是“重新判断用户意图”。

## 目标

这一层当前只解决三件事：

- 把 `router_plan` 规范化为可用的 prompt 资产选择
- 生成 `BranchStrategy`
- 组装 responder messages

## 当前主链

```text
RouteDecision + router_plan
-> build_turn_plan
-> build_strategy_from_model_plan
-> BranchStrategy
-> build_responder_messages
-> TurnPlan
```

## 这一步到底做什么

`build_turn_plan()` 当前职责很窄，也很明确：

1. 接收 Router 阶段产出的 snapshot。
2. 如有需要，把 router-profile snapshot 升级成 responder 所需的上下文。
3. 保留上游已经产出的 `router_plan`。
4. 调用 `model_plan_builder.py` 把 `router_plan` 直接转成 `BranchStrategy`。
5. 按这个 `BranchStrategy` 组装 responder `messages`。

这一层当前不会再做：

- 再跑一次意图识别
- scene-specific builder 二次分流
- 教育分支本地 selector 判定
- turn frame resolver
- module / subject / style selector
- mode selector

换句话说，Orchestration 现在不负责“选什么”，只负责“把已经选好的东西落成可执行回复计划”。

## `router_plan` 如何被消费

### Education

如果 `turn_scene=education`，`router_plan` 通常至少包含：

- `module`
- `subject`
- `style`
- `policy_id`
- `primary_scenario`
- `primary_action`
- `learning_objects`
- `object_scope`
- `object_continuity`
- `answer_boundary`

`model_plan_builder.py` 在教育分支里只做三类事情：

- 校验这些 id 是否存在于 prompt 资产里
- 缺失时补一个安全默认值
- 从 `plugin/module/subject/style` Markdown 资产装配 `BranchStrategy`

它不会再根据用户文本重新决定“到底该 explain 还是 solve”。

### General / Chat / Clarify

如果 `turn_scene` 是非教育分支，`router_plan` 主要包含：

- `mode`

`model_plan_builder.py` 会把这个 `mode` 映射到对应的 mode asset，然后生成 `BranchStrategy`。

## responder messages 在这里怎么组

当前 responder message 组装规则是：

- `messages` 会附最近几轮原始 `history_messages`
- system prompt 只保留短摘要，不再重复展开长历史
- 当前用户输入、当前附件、继承参考附件会继续进入上下文

这样做的目的很直接：

- Router 已经用历史判定过当前轮意图
- responder 仍然需要看见原始 Q/A，才能在实际回答时接得自然
- 但 system prompt 不再把同一份历史重复写一遍

## 默认值与兜底

如果 Router 成功返回了 `RouteDecision`，但 `plan` 缺失、不完整，或者模型调用失败后走了 heuristic fallback：

- `RouterService` 会先补一个本地 `router_plan`
- `build_turn_plan()` 依然只消费这个 `router_plan`
- 主链不会再退回旧规则系统

所以当前主链保证的是：

- 上游始终产出 `router_plan`
- 下游始终直接消费 `router_plan`

## 关键文件

- [dispatcher.py](/app/streaming-ava/ava/application/orchestration/dispatcher.py)
  - `build_turn_plan()` 统一入口
- [model_plan_builder.py](/app/streaming-ava/ava/application/orchestration/model_plan_builder.py)
  - 把 `router_plan` 直接转成 `BranchStrategy`
- [common.py](/app/streaming-ava/ava/application/orchestration/common.py)
  - responder messages 组装
- [types.py](/app/streaming-ava/ava/application/orchestration/types.py)
  - `TurnPlan`

## 当前设计约束

- `build_turn_plan()` 不再承担第二轮策略判断
- `module / subject / style / mode` 以 `router_plan` 为准
- 这一层的主要工作是“校验、补默认值、装配资产”
- responder 默认附加最近几轮 `history_messages`
- 如果历史原始问答已经进 `messages`，system prompt 只保留短摘要
- reference artifacts 只在上下文明确连续时继承

## 与其他模块关系

- 上游来自 [routing/README.md](/app/streaming-ava/ava/application/routing/README.md)
- prompt 资产解析来自 [ava/infrastructure/prompts/runtime.py](/app/streaming-ava/ava/infrastructure/prompts/runtime.py)
- responder system prompt 组装来自 [ava/infrastructure/prompts/prompt_builder.py](/app/streaming-ava/ava/infrastructure/prompts/prompt_builder.py)
