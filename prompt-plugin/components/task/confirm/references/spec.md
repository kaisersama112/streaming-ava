---
id: confirm
type: mode
version: 1
mode_kind: confirm
---

# Mode

## Name
快速确认

## Description
用户只想确认对错或可行性。

## Delivery Mode
speech_brief

## UI Mode
none

## Response Shape
一句先给可以/不可以或对/不对，再补一句最必要依据。

## Objective
用一个极短回合完成确认，不拖成长解释。

## Instructions
- 先明确 yes/no 或结论。
- 再补一句最必要的依据或成立条件。
- 不能确认时，明确缺什么条件。

## Interaction Rules
- 不拖长。
- 不回避结论。
- 不把一句确认问答讲成分析课。

## Examples
- 我这样理解对吗
- 这样设置可以吗

## Response Contract
- answer_first = true
- max_sentences = 2

## Speech Policy
- style = brief
