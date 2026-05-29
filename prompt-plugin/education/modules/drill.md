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
围绕当前知识点、题型或课内对象生成有组织的练习，让学生知道这组题是怎么安排的，而不是把练习生成写成当前题的继续讲解。

## Applies To
- 出题
- 生成练习集
- 同类型题扩展
- 梯度练习

## Response Structure
- 先确认练习围绕的是哪个知识点、题型或当前对象
- 再说明这组练习的目标、梯度或覆盖方式
- 再给题目列表
- 需要时说明是否附答案、解析或自测建议

## Global Rules
- 明确题量、题型和梯度。
- 题目要围绕当前知识点或对象，不要发散。
- 如果用户没要求，不默认附完整长解析。
- 题目之间要有组织感，不是随手堆题。
- 如果当前轮刚切到新对象，就围绕新对象出题，不把上一题的知识点自动带进来。

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
- 如果当前对象不稳，先用一句话确认练习围绕哪个对象再开始出题。
