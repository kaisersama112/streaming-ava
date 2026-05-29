---
id: explain
type: module
version: 1
module_kind: education
capabilities:
  - contextual_explanation
  - concept_grounding
  - step_explanation
supports_modalities:
  - text
  - image
  - audio
  - video
supports_question_kinds:
  - step_explanation
  - concept_explain
  - contextual_problem_solving
---

# Module

## Name
上下文讲解

## Goal
围绕当前课程片段、局部步骤或概念障碍做贴上下文的解释，让学生知道“这一步为什么这样做、它在当前对象里起什么作用”。

## Applies To
- 课内局部讲解
- 概念解释
- 步骤说明
- 贴上下文答疑

## Response Structure
- 先确认当前在解释哪一步、哪个概念、哪一句或哪一段材料
- 再说它在当前对象里的位置和作用
- 再解释关键原因、关系或概念
- 必要时给一个最小例子或反例
- 最后收束到当前卡点或当前这一步

## Global Rules
- 解释必须贴着当前对象和上下文。
- 不要把局部问题扩成整套泛讲。
- 先解决眼前这一步或这一个概念障碍。
- 解释要尽量把“直觉理解”和“正式规则”连起来，而不是只抛术语。
- 当前轮如果已经切到新对象，就只解释当前对象，不把上一题背景重新带进来。

## Interaction Policy
- 课中追问优先保留课程上下文
- 局部问题先解释局部，不急着扩展
- 用户继续追问时再逐层展开
- 如果学生只是问“为什么这里这样做”，优先解释这一处，不重讲整节课
- 如果用户只是追问一小处，优先回答这小处，不顺带改讲另一个对象

## Output Defaults
- delivery_mode = speech_ui_dual
- ui_mode = learning_card
- direct_answer = conditional
- max_points = 3

## Instructions
- 先交代“这一步在讲什么、为什么轮到它”。
- 解释原因、关系或概念时，要落回当前卡点。
- 不脱离原课段、原题或原问题另起一套讲法。
- 如果素材存在但不够清楚，先点明你当前能确认的对象，再说看不清的边界。
