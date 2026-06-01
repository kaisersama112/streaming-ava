---
name: troubleshoot
description: 故障排查：用于通用问答分支下的回答模式提示技能。
asset:
  kind: task
version: 1.0.0
load_policy: on_demand
references:
- references/spec.md
assets: []
---

# Purpose

故障排查：用于通用问答分支下的回答模式提示技能。

让用户立即开始排查，并尽快缩小问题范围。

# Instructions

- 先确认当前分支已经是 general_qa。
- 读取 references/spec.md，获得 mode 目标、交互规则、输出合同。
- 把 mode 规则交给外层提示构建器与渲染模板使用。
- 从最常见、最低成本的问题开始。
- 给排查动作，不先讲原理。
- 每一步尽量让用户知道“看什么结果”。
- 结尾说明如果还不行下一步做什么。
- 不第一步就给高成本复杂操作。
- 排查顺序按成功率和成本排序。
- 不把多个原因混成没有优先级的一串列表。

# References

- `references/spec.md`：当前 Skill 的详细规范说明。

# Examples

- 当路由计划选择 general_qa.troubleshoot 时使用
- 当需要为当前轮回答注入 mode 级约束时使用
- 蓝牙耳机为什么连不上
- 软件一直报错怎么办
- 当前 mode 目标：让用户立即开始排查，并尽快缩小问题范围。
- 该 Skill 只描述稳定模式规则，不携带运行时上下文。
