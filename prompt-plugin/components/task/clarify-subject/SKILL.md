---
name: clarify-subject
description: 学科任务边界：用于澄清分支下的最小追问模式提示技能。
asset:
  kind: task
version: 1.0.0
load_policy: on_demand
references:
- references/spec.md
assets: []
---

# Purpose

学科任务边界：用于澄清分支下的最小追问模式提示技能。

避免系统在错误领域里展开回答。

# Instructions

- 先确认当前分支已经是 clarify。
- 读取 references/spec.md，获得 mode 目标、交互规则、输出合同。
- 把 mode 规则交给外层提示构建器与渲染模板使用。
- 只澄清一个最关键边界。
- 问句保持自然。
- 能把边界收成最少两个方向时，就不要列太多选项。
- 不一次问多个维度。
- 不提前答任何一个方向。

# References

- `references/spec.md`：当前 Skill 的详细规范说明。

# Examples

- 当路由计划选择 clarify.subject 时使用
- 当需要为当前轮回答注入 mode 级约束时使用
- 你是想问数学题，还是物理实验这个现象
- 当前 mode 目标：避免系统在错误领域里展开回答。
- 该 Skill 只描述稳定模式规则，不携带运行时上下文。
