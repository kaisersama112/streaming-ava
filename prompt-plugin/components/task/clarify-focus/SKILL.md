---
name: clarify-focus
description: 素材焦点：用于澄清分支下的最小追问模式提示技能。
asset:
  kind: task
version: 1.0.0
load_policy: on_demand
references:
- references/spec.md
assets: []
---

# Purpose

素材焦点：用于澄清分支下的最小追问模式提示技能。

让下一轮能够聚焦一个清晰的分析点。

# Instructions

- 先确认当前分支已经是 clarify。
- 读取 references/spec.md，获得 mode 目标、交互规则、输出合同。
- 把 mode 规则交给外层提示构建器与渲染模板使用。
- 只问一个焦点问题。
- 把问题缩到最可能的关注点。
- 能结合当前素材内容缩小范围时，就不要空问“你想看什么”。
- 不把素材所有部分都列一遍。
- 不在澄清阶段做完整分析。

# References

- `references/spec.md`：当前 Skill 的详细规范说明。

# Examples

- 当路由计划选择 clarify.focus 时使用
- 当需要为当前轮回答注入 mode 级约束时使用
- 帮我看一下
- 讲讲这个
- 当前 mode 目标：让下一轮能够聚焦一个清晰的分析点。
- 该 Skill 只描述稳定模式规则，不携带运行时上下文。
