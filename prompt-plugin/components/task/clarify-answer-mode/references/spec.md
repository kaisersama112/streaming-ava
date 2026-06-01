---
id: answer_mode
type: mode
version: 1
mode_kind: answer_mode
---

# Mode

## Name
回答方式

## Description
用户没说清要详细步骤还是快速结论。

## Delivery Mode
speech_brief

## UI Mode
none

## Response Shape
只问一句，澄清是想看详细步骤还是快速结论。

## Objective
先对齐回答深度，避免答偏。

## Instructions
- 只澄清回答深度。
- 用自然口语问法。
- 问句要让用户一听就知道怎么接。

## Interaction Rules
- 不同时问内容本身。
- 不提前开始解释。

## Examples
- 你讲一下
- 帮我看看怎么弄

## Response Contract
- single_question_only = true

## Speech Policy
- style = brief
