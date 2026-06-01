---
name: backchannel
description: 实时短反馈：用于闲聊分支下的互动模式提示技能。
asset:
  kind: task
version: 1.0.0
load_policy: on_demand
references:
- references/spec.md
assets: []
---

# Purpose

实时短反馈：用于闲聊分支下的互动模式提示技能。

维持实时对话感，不抢占说话时间。

# Instructions

- 先确认当前分支已经是 casual_chat。
- 读取 references/spec.md，获得 mode 目标、交互规则、输出合同。
- 把 mode 规则交给外层提示构建器与渲染模板使用。
- 极短。
- 只表达“在听/在跟/收到”。
- 语气自然，不像系统播报。
- 不引入新信息。
- 不扩展成正式回答。

# References

- `references/spec.md`：当前 Skill 的详细规范说明。

# Examples

- 当路由计划选择 casual_chat.backchannel 时使用
- 当需要为当前轮回答注入 mode 级约束时使用
- 在吗
- 好的
- 当前 mode 目标：维持实时对话感，不抢占说话时间。
- 该 Skill 只描述稳定模式规则，不携带运行时上下文。
