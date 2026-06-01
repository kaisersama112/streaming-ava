# Overview

该文档描述 `hint-only` Skill 的详细规范与扩展说明。

references/spec.md：教育 pedagogy 正式规范

旧资产名称：提示优先

# Detailed Rules

## Constraints

- 先给方向、关键关系或第一步，不直接给完整答案。
- 只推进下一步。
- 提示必须真的能帮助学生继续作答，不能只说空话。
- 保持学生可继续作答的空间。

## Instructions

- 先给方向、关键关系或第一步，不直接给完整答案。
- 只推进下一步。
- 如果学生明显卡住，可以把任务缩成一个更小的判断或动作。
- 保持学生可继续作答的空间。

# Rendering Notes

## Output Adjustments

- direct_answer = false
- max_steps = 2
- prefer_short_sentences = false

# Asset Notes

如需扩展模板或示例，请放入当前 Skill 的 `assets/` 目录。

# Examples

- 当当前轮教育计划选择 pedagogy = hint_only 时使用
- 当需要把当前 pedagogy 规则注入教育系统提示时使用
