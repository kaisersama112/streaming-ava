---
id: missing_material
type: mode
version: 1
mode_kind: missing_material
---

# Mode

## Name
素材缺失

## Description
用户提到了题目、图片、音频或视频，但当前轮没给素材。

## Delivery Mode
speech_brief

## UI Mode
none

## Response Shape
只问一句需要补什么素材，不附带解释。

## Objective
补齐当前回答真正缺失的附件或题面。

## Instructions
- 直接指出缺哪类素材。
- 只问一个补素材问题。
- 如果缺的是题面、截图、音频或视频，要说得具体可执行。

## Interaction Rules
- 不同时追问多个附件。
- 不预设素材内容。

## Examples
- 帮我看看这道题
- 这个视频帮我讲一下

## Response Contract
- single_question_only = true

## Speech Policy
- style = brief
