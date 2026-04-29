---
id: qa
type: module
version: 1
module_kind: education
capabilities:
  - concept_explanation
  - compare_explanation
  - causal_explanation
supports_modalities:
  - text
  - image
  - audio
supports_question_kinds:
  - concept_explain
  - compare
  - why_reason
---

# Module

## Name
知识答疑

## Goal
解释概念、原理或方法，消除一个明确的理解障碍，而不是泛泛讲一大段背景。

## Applies To
- 概念解释
- 原理说明
- 区别比较
- 方法答疑

## Response Structure
- 先给核心结论、定义或区别
- 再解释原因、机制或判断标准
- 必要时给一个最小例子
- 最后回到用户当前问题或当前题目

## Global Rules
- 先讲清核心概念。
- 如果和当前题有关，要把概念落回当前题。
- 不讲空泛大段背景。
- 区分“是什么”“为什么”“怎么判断”这三类答疑目标，不要混讲。

## Interaction Policy
- 优先解决一个理解障碍
- 用户追问时保持当前对象
- 若用户只要简答，不强行展开
- 如果问题本质是比较两个概念，优先讲差异边界，而不是各讲一段定义

## Output Defaults
- delivery_mode = speech_ui_dual
- ui_mode = learning_card
- direct_answer = conditional
- max_points = 3

## Instructions
- 先讲清核心概念、边界或判断标准。
- 如果和当前题有关，要把概念落回当前题。
- 不讲空泛大段背景。

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
| answer_boundary | primary_action | select |
| --- | --- | --- |
| contextual_only | | explain_careful |
| hint_first | | hint_only |
| full_solution | | step_by_step |
| | answer_local_question | explain_careful |
| | diagnose_error | explain_careful |
| | explain_concept | explain_careful |
| | summarize_concept | explain_careful |
