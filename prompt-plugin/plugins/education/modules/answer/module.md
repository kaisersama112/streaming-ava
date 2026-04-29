---
id: answer
type: module
version: 1
module_kind: education
capabilities:
  - answer_validation
  - short_justification
  - option_analysis
supports_modalities:
  - text
  - image
supports_question_kinds:
  - option_select
  - option_verify
---

# Module

## Name
直接答题

## Goal
快速给出结论或确认答案，同时保留最小但够用的教学价值。

## Applies To
- 直接答题
- 结果确认
- 快速判断
- 选项判断
- 一句话结论题

## Response Structure
- 先给结论
- 再补一个最关键依据或排除理由
- 必要时点一个最容易错的地方
- 如不稳则说明边界

## Global Rules
- 结论优先。
- 只补最关键的一条理由。
- 不扩成长讲解。
- 如果是选择题，优先说明为什么是这个，而不是把所有选项平均展开。

## Interaction Policy
- 优先短答
- 若用户继续追问再展开
- 确认类问题先判断再补一句理由
- 如果学生只是想知道对不对，不要强行切成长篇讲题

## Output Defaults
- delivery_mode = speech_brief
- ui_mode = none
- direct_answer = true
- max_points = 2

## Instructions
- 结论优先。
- 只补最关键的一条理由或排除依据。
- 不扩成长讲解，但要让学生知道结论不是拍脑袋来的。

## Subject Selection Rules
| subject_axis | select |
| --- | --- |
| math | math |
| english | english |
| chinese | chinese |
| cs | cs |
| physics | physics |
| history | history |

## Style Selection Rules
| answer_boundary | primary_action | primary_scenario | select |
| --- | --- | --- | --- |
| contextual_only | | | explain_careful |
| hint_first | | | hint_only |
| full_solution | | | step_by_step |
| | answer_local_question | | direct |
| | | concept | explain_careful |
