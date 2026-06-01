---
name: hint-only
description: 提示优先：用于教育场景下的教学法提示技能。
asset:
  kind: method
version: 1.0.0
load_policy: on_demand
references:
- references/spec.md
assets: []
---

# Purpose

提示优先：用于教育场景下的教学法提示技能。

默认表达风格：guiding

# Instructions

- 先确认当前轮已经进入 education 分支。
- 读取 references/spec.md，拿到当前 pedagogy 的稳定规则。
- 与教育分支、其它教育层资产组合后，再交给外层提示渲染器。
- 先给方向、关键关系或第一步，不直接给完整答案。
- 只推进下一步。
- 如果学生明显卡住，可以把任务缩成一个更小的判断或动作。
- 保持学生可继续作答的空间。
- 提示必须真的能帮助学生继续作答，不能只说空话。

# References

- `references/spec.md`：当前 Skill 的详细规范说明。

# Examples

- 当当前轮教育计划选择 pedagogy = hint_only 时使用
- 当需要把当前 pedagogy 规则注入教育系统提示时使用
- 当前资产核心作用：guiding
- 该 Skill 不负责选择逻辑，选择由 ava/router_selector 决定。
