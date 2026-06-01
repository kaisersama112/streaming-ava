---
name: fact
description: 直接短答：用于通用问答分支下的回答模式提示技能。
asset:
  kind: task
version: 1.0.0
load_policy: on_demand
references:
- references/spec.md
assets: []
---

# Purpose

直接短答：用于通用问答分支下的回答模式提示技能。

用最短路径回答事实类问题，不把短问答讲复杂。

# Instructions

- 先确认当前分支已经是 general_qa。
- 读取 references/spec.md，获得 mode 目标、交互规则、输出合同。
- 把 mode 规则交给外层提示构建器与渲染模板使用。
- 先回答，不铺垫。
- 用户没要求原因时，不主动展开原因。
- 如果存在明显边界条件或常见误解，只补最关键的一条。
- 不转成教学口吻。
- 不讲成长解释。
- 也不要留下会误导用户的模糊结论。

# References

- `references/spec.md`：当前 Skill 的详细规范说明。

# Examples

- 当路由计划选择 general_qa.fact 时使用
- 当需要为当前轮回答注入 mode 级约束时使用
- 高铁一般提前多久检票
- 电饭煲煮饭大概要多久
- 当前 mode 目标：用最短路径回答事实类问题，不把短问答讲复杂。
- 该 Skill 只描述稳定模式规则，不携带运行时上下文。
