---
name: clarify-missing-material
description: 素材缺失：用于澄清分支下的最小追问模式提示技能。
asset:
  kind: task
version: 1.0.0
load_policy: on_demand
references:
- references/spec.md
assets: []
---

# Purpose

素材缺失：用于澄清分支下的最小追问模式提示技能。

补齐当前回答真正缺失的附件或题面。

# Instructions

- 先确认当前分支已经是 clarify。
- 读取 references/spec.md，获得 mode 目标、交互规则、输出合同。
- 把 mode 规则交给外层提示构建器与渲染模板使用。
- 直接指出缺哪类素材。
- 只问一个补素材问题。
- 如果缺的是题面、截图、音频或视频，要说得具体可执行。
- 不同时追问多个附件。
- 不预设素材内容。

# References

- `references/spec.md`：当前 Skill 的详细规范说明。

# Examples

- 当路由计划选择 clarify.missing_material 时使用
- 当需要为当前轮回答注入 mode 级约束时使用
- 帮我看看这道题
- 这个视频帮我讲一下
- 当前 mode 目标：补齐当前回答真正缺失的附件或题面。
- 该 Skill 只描述稳定模式规则，不携带运行时上下文。
