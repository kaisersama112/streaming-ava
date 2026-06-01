---
name: direct
description: 直接结论：用于教育场景下的教学法提示技能。
asset:
  kind: method
version: 1.0.0
load_policy: on_demand
references:
- references/spec.md
assets: []
---

# Purpose

直接结论：用于教育场景下的教学法提示技能。

默认表达风格：concise

# Instructions

- 先确认当前轮已经进入 education 分支。
- 读取 references/spec.md，拿到当前 pedagogy 的稳定规则。
- 与教育分支、其它教育层资产组合后，再交给外层提示渲染器。
- 先给明确结论。
- 只补最硬的一条依据或判断标准。
- 不扩成长讲解，但不要让结论显得像拍脑袋。
- 必要时点一个最容易错的地方。
- 不扩成长讲解。

# References

- `references/spec.md`：当前 Skill 的详细规范说明。

# Examples

- 当当前轮教育计划选择 pedagogy = direct 时使用
- 当需要把当前 pedagogy 规则注入教育系统提示时使用
- 当前资产核心作用：concise
- 该 Skill 不负责选择逻辑，选择由 ava/router_selector 决定。
