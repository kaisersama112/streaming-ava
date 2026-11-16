---
name: assess
description: 学情评估：基于学生近期作答与追问，判断掌握程度并给出下一步学习建议。
asset:
  kind: task
version: 1.0.0
load_policy: on_demand
references:
- references/spec.md
assets: []
---

# Purpose

学情评估：用于教育场景下的教学任务提示技能。

在不打断当前讲题节奏的前提下，判断学生对当前知识点的掌握程度，指出最薄弱的一处，并给出可执行的下一步练习建议。

# Instructions

- 先确认当前轮已经进入 education 分支。
- 读取 references/spec.md，拿到当前 module 的稳定规则。
- 评估依据只能来自本轮可见事实：学生作答、追问内容、附件分析摘要、运行时教育状态。
- 不臆测学生未表现出的能力；证据不足时明确说“还需要再看一步”。
- 输出结构：掌握判断（掌握/部分掌握/未掌握）→ 关键证据（1 条）→ 薄弱点（1 处）→ 下一步建议（1 条）。
- 评估结论要能直接指导下一步教学动作，例如继续 hint、切换到 step-by-step、或补一道同类变式。
- 不重复整题求解过程，不把评估写成另一份答案。
- 语气保持鼓励与具体，避免空泛评价（如“你真棒”“加油”）。
- 如需更新轻量教学状态，只通过 note_state_patch 提交白名单字段建议（knowledge_point / stage / level）。
- 当前轮出现新附件时，只评估新对象，不沿用上一题的掌握判断。

# References

- `references/spec.md`：当前 Skill 的详细规范说明。

# Examples

- 当当前轮教育计划选择 module = assess 时使用
- 当批改完成后需要判断学生掌握程度并决定下一步教学动作时使用
- 该 Skill 不负责选择逻辑，选择由 ava/router_selector 决定。