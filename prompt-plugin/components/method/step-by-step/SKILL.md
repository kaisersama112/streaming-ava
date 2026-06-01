---
name: step-by-step
description: 分步引导：用于教育场景下的教学法提示技能。
asset:
  kind: method
version: 1.0.0
load_policy: on_demand
references:
- references/spec.md
assets: []
---

# Purpose

分步引导：用于教育场景下的教学法提示技能。

默认表达风格：structured

# Instructions

- 先确认当前轮已经进入 education 分支。
- 读取 references/spec.md，拿到当前 pedagogy 的稳定规则。
- 与教育分支、其它教育层资产组合后，再交给外层提示渲染器。
- 分步讲，不跳步。
- 每一步只推进一个关键点，并让学生知道这一步的目的。
- 上一步没站稳时，不要偷跑到下一步。
- 不一口气把所有细节讲完。

# References

- `references/spec.md`：当前 Skill 的详细规范说明。

# Examples

- 当当前轮教育计划选择 pedagogy = step_by_step 时使用
- 当需要把当前 pedagogy 规则注入教育系统提示时使用
- 当前资产核心作用：structured
- 该 Skill 不负责选择逻辑，选择由 ava/router_selector 决定。
