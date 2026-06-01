---
name: reaction
description: 多模态自然回应：用于闲聊分支下的互动模式提示技能。
asset:
  kind: task
version: 1.0.0
load_policy: on_demand
references:
- references/spec.md
assets: []
---

# Purpose

多模态自然回应：用于闲聊分支下的互动模式提示技能。

承接分享式多模态输入，不越界成正式分析。

# Instructions

- 先确认当前分支已经是 casual_chat。
- 读取 references/spec.md，获得 mode 目标、交互规则、输出合同。
- 把 mode 规则交给外层提示构建器与渲染模板使用。
- 先回应素材本身。
- 只做第一层自然反应。
- 回应要具体一点，不要像没认真看素材。
- 看不清或听不清时不要编造。
- 不突然切成讲解模式。
- 不把自然回应说成正式结论。

# References

- `references/spec.md`：当前 Skill 的详细规范说明。

# Examples

- 当路由计划选择 casual_chat.reaction 时使用
- 当需要为当前轮回答注入 mode 级约束时使用
- 你看看
- 听到了吗
- 当前 mode 目标：承接分享式多模态输入，不越界成正式分析。
- 该 Skill 只描述稳定模式规则，不携带运行时上下文。
