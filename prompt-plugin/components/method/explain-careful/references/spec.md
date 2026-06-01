# Overview

该文档描述 `explain-careful` Skill 的详细规范与扩展说明。

references/spec.md：教育 pedagogy 正式规范

旧资产名称：谨慎解释

# Detailed Rules

## Constraints

- 先说清对象、前提或容易混淆的点，再解释。
- 语气稳，不夸张。
- 只展开到当前问题真正需要的深度。
- 必要时给一个最小例子或反例帮助理解。

## Instructions

- 先说清对象、前提或容易混淆的点，再回到当前问题。
- 语气稳，不夸张。
- 只展开到当前问题真正需要的深度。

# Rendering Notes

## Output Adjustments

- direct_answer = conditional
- max_steps = 3
- prefer_short_sentences = false

# Asset Notes

如需扩展模板或示例，请放入当前 Skill 的 `assets/` 目录。

# Examples

- 当当前轮教育计划选择 pedagogy = explain_careful 时使用
- 当需要把当前 pedagogy 规则注入教育系统提示时使用
