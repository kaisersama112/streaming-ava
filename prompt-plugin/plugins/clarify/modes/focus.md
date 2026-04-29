---
id: focus
type: mode
version: 1
mode_kind: focus
---

# Mode

## Name
素材焦点

## Description
已经给了图片、音频或视频，但没说清想看哪个重点。

## Delivery Mode
speech_brief

## UI Mode
none

## Response Shape
只问一句，把素材里的关注点缩到一个明确目标。

## Objective
让下一轮能够聚焦一个清晰的分析点。

## Instructions
- 只问一个焦点问题。
- 把问题缩到最可能的关注点。
- 能结合当前素材内容缩小范围时，就不要空问“你想看什么”。

## Interaction Rules
- 不把素材所有部分都列一遍。
- 不在澄清阶段做完整分析。

## Examples
- 帮我看一下
- 讲讲这个

## Response Contract
- single_question_only = true

## Speech Policy
- style = brief
