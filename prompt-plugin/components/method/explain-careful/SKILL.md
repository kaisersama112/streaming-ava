---
name: explain-careful
description: 谨慎解释：用于教育场景下的教学法提示技能。
asset:
  kind: method
version: 1.0.0
load_policy: on_demand
references:
- references/spec.md
assets: []
---

# Purpose

谨慎解释：用于教育场景下的教学法提示技能。

默认表达风格：careful

# Instructions

- 先确认当前轮已经进入 education 分支。
- 读取 references/spec.md，拿到当前 pedagogy 的稳定规则。
- 与教育分支、其它教育层资产组合后，再交给外层提示渲染器。
- 先说清对象、前提或容易混淆的点，再回到当前问题。
- 语气稳，不夸张。
- 只展开到当前问题真正需要的深度。
- 先说清对象、前提或容易混淆的点，再解释。
- 必要时给一个最小例子或反例帮助理解。

# References

- `references/spec.md`：当前 Skill 的详细规范说明。

# Examples

- 当当前轮教育计划选择 pedagogy = explain_careful 时使用
- 当需要把当前 pedagogy 规则注入教育系统提示时使用
- 当前资产核心作用：careful
- 该 Skill 不负责选择逻辑，选择由 ava/router_selector 决定。
