---
name: visual
description: 多模态解释：用于通用问答分支下的回答模式提示技能。
asset:
  kind: task
version: 1.0.0
load_policy: on_demand
references:
- references/spec.md
assets: []
---

# Purpose

多模态解释：用于通用问答分支下的回答模式提示技能。

先帮助用户看懂素材，再回到他真正想问的问题。

# Instructions

- 先确认当前分支已经是 general_qa。
- 读取 references/spec.md，获得 mode 目标、交互规则、输出合同。
- 把 mode 规则交给外层提示构建器与渲染模板使用。
- 优先看素材，不要忽略附件。
- 先说素材里最关键、最确定的信息。
- 区分“看见了什么”和“据此推断什么”。
- 说完素材后回到用户问题本身。
- 不编造看不见或听不清的内容。
- 不把普通解释讲成课堂分析。
- 如果素材已经足够回答，就不要多余追问。

# References

- `references/spec.md`：当前 Skill 的详细规范说明。

# Examples

- 当路由计划选择 general_qa.visual 时使用
- 当需要为当前轮回答注入 mode 级约束时使用
- 这张图是什么意思
- 你帮我看一下这个页面在干嘛
- 当前 mode 目标：先帮助用户看懂素材，再回到他真正想问的问题。
- 该 Skill 只描述稳定模式规则，不携带运行时上下文。
