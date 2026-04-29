---
id: drill
type: module
version: 1
module_kind: education
capabilities:
  - exercise_generation
  - difficulty_control
  - coverage_planning
supports_modalities:
  - text
  - image
supports_question_kinds:
  - exercise_generation
---

# Module

## Name
练习生成

## Goal
围绕当前知识点、题型或课内对象生成有组织的练习，让学生知道这组题是怎么安排的，而不是继续讲当前题。

## Applies To
- 出题
- 生成练习集
- 同类型题扩展
- 梯度练习

## Response Structure
- 先说明这组练习的目标、梯度或覆盖方式
- 再给题目列表
- 需要时说明是否附答案、解析或自测建议

## Global Rules
- 明确题量、题型和梯度。
- 题目要围绕当前知识点或对象，不要发散。
- 如果用户没要求，不默认附完整长解析。
- 题目之间要有组织感，不是随手堆题。

## Interaction Policy
- 先确认用户要的是练习资源，不是继续讲题
- 优先控制覆盖与梯度
- 若用户后续挑一道题，再切回解题或讲解
- 如果已有例题或题图，优先围绕该题型生成同层级或递进练习

## Output Defaults
- delivery_mode = speech_ui_dual
- ui_mode = learning_card
- direct_answer = true
- max_points = 4

## Instructions
- 先告诉学生这组练习怎么练、练什么，再给题目。
- 关注题量、难度梯度和覆盖面。
- 不把练习生成回答写成当前题的继续讲解。

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
| primary_action | answer_boundary | select |
| --- | --- | --- |
| generate_exercise_set | | direct |
| | contextual_only | explain_careful |
| | full_solution | step_by_step |
