# Overview

该文档描述 `step-by-step` Skill 的详细规范与扩展说明。

references/spec.md：教育 pedagogy 正式规范

旧资产名称：分步引导

# Detailed Rules

## Constraints

- 分步讲，不跳步。
- 每一步只推进一个关键点，并让学生知道这一步的目的。
- 上一步没站稳时，不要偷跑到下一步。
- 不一口气把所有细节讲完。

## Instructions

- 分步讲，不跳步。
- 每一步只推进一个关键点，并让学生知道这一步的目的。
- 上一步没站稳时，不要偷跑到下一步。
- 不一口气把所有细节讲完。

# Rendering Notes

## Output Adjustments

- direct_answer = false
- max_steps = 3
- prefer_short_sentences = false

# Asset Notes

如需扩展模板或示例，请放入当前 Skill 的 `assets/` 目录。

# Examples

- 当当前轮教育计划选择 pedagogy = step_by_step 时使用
- 当需要把当前 pedagogy 规则注入教育系统提示时使用
