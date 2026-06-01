---
name: clarify-answer-mode
description: 回答方式：用于澄清分支下的最小追问模式提示技能。
asset:
  kind: task
version: 1.0.0
load_policy: on_demand
references:
- references/spec.md
assets: []
---

# Purpose

回答方式：用于澄清分支下的最小追问模式提示技能。

先对齐回答深度，避免答偏。

# Instructions

- 先确认当前分支已经是 clarify。
- 读取 references/spec.md，获得 mode 目标、交互规则、输出合同。
- 把 mode 规则交给外层提示构建器与渲染模板使用。
- 只澄清回答深度。
- 用自然口语问法。
- 问句要让用户一听就知道怎么接。
- 不同时问内容本身。
- 不提前开始解释。

# References

- `references/spec.md`：当前 Skill 的详细规范说明。

# Examples

- 当路由计划选择 clarify.answer_mode 时使用
- 当需要为当前轮回答注入 mode 级约束时使用
- 你讲一下
- 帮我看看怎么弄
- 当前 mode 目标：先对齐回答深度，避免答偏。
- 该 Skill 只描述稳定模式规则，不携带运行时上下文。
