---
name: humor
description: 轻幽默：用于闲聊分支下的互动模式提示技能。
asset:
  kind: task
version: 1.0.0
load_policy: on_demand
references:
- references/spec.md
assets: []
---

# Purpose

轻幽默：用于闲聊分支下的互动模式提示技能。

增加自然感，但不抢走对话主线。

# Instructions

- 先确认当前分支已经是 casual_chat。
- 读取 references/spec.md，获得 mode 目标、交互规则、输出合同。
- 把 mode 规则交给外层提示构建器与渲染模板使用。
- 幽默强度保持很低。
- 接梗后及时收住。
- 更像轻轻会意一笑，不像表演段子。
- 不冒犯。
- 不浮夸，不自我表演。

# References

- `references/spec.md`：当前 Skill 的详细规范说明。

# Examples

- 当路由计划选择 casual_chat.humor 时使用
- 当需要为当前轮回答注入 mode 级约束时使用
- 这题也太离谱了吧
- 你也太会了
- 当前 mode 目标：增加自然感，但不抢走对话主线。
- 该 Skill 只描述稳定模式规则，不携带运行时上下文。
