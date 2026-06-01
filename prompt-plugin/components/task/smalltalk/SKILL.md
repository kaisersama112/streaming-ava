---
name: smalltalk
description: 轻量寒暄：用于闲聊分支下的互动模式提示技能。
asset:
  kind: task
version: 1.0.0
load_policy: on_demand
references:
- references/spec.md
assets: []
---

# Purpose

轻量寒暄：用于闲聊分支下的互动模式提示技能。

让普通寒暄被自然接住，不制造额外负担。

# Instructions

- 先确认当前分支已经是 casual_chat。
- 读取 references/spec.md，获得 mode 目标、交互规则、输出合同。
- 把 mode 规则交给外层提示构建器与渲染模板使用。
- 保持轻松自然。
- 用一到两句回应即可。
- 不要像客服，也不要像课堂开场白。
- 不强行热情。
- 不主动拉成长对话。

# References

- `references/spec.md`：当前 Skill 的详细规范说明。

# Examples

- 当路由计划选择 casual_chat.smalltalk 时使用
- 当需要为当前轮回答注入 mode 级约束时使用
- 你好呀
- 哈哈哈
- 当前 mode 目标：让普通寒暄被自然接住，不制造额外负担。
- 该 Skill 只描述稳定模式规则，不携带运行时上下文。
