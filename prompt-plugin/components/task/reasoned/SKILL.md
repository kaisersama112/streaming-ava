---
name: reasoned
description: 结论加原因：用于通用问答分支下的回答模式提示技能。
asset:
  kind: task
version: 1.0.0
load_policy: on_demand
references:
- references/spec.md
assets: []
---

# Purpose

结论加原因：用于通用问答分支下的回答模式提示技能。

先解决“是什么/会不会”，再用最短理由满足解释需求。

# Instructions

- 先确认当前分支已经是 general_qa。
- 读取 references/spec.md，获得 mode 目标、交互规则、输出合同。
- 把 mode 规则交给外层提示构建器与渲染模板使用。
- 结论优先。
- 原因只说最关键的一层。
- 必要时补一个最关键的前提或边界。
- 不引入多个平行原因。
- 不写成长科普。
- 不使用教学式追问。
- 不把一句理由拆成绕弯子的话。

# References

- `references/spec.md`：当前 Skill 的详细规范说明。

# Examples

- 当路由计划选择 general_qa.reasoned 时使用
- 当需要为当前轮回答注入 mode 级约束时使用
- 为什么手机会发烫
- 为什么图片发不出去
- 当前 mode 目标：先解决“是什么/会不会”，再用最短理由满足解释需求。
- 该 Skill 只描述稳定模式规则，不携带运行时上下文。
