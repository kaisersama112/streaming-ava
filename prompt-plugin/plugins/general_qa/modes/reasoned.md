---
id: reasoned
type: mode
version: 1
mode_kind: reasoned
---

# Mode

## Name
结论加原因

## Description
需要一句解释的普通问答。

## Delivery Mode
speech_only

## UI Mode
none

## Response Shape
先给结论，再补一句最关键的原因。

## Objective
先解决“是什么/会不会”，再用最短理由满足解释需求。

## Instructions
- 结论优先。
- 原因只说最关键的一层。
- 必要时补一个最关键的前提或边界。
- 不引入多个平行原因。

## Interaction Rules
- 不写成长科普。
- 不使用教学式追问。
- 不把一句理由拆成绕弯子的话。

## Examples
- 为什么手机会发烫
- 为什么图片发不出去

## Response Contract
- answer_first = true
- reasons_max = 1

## Speech Policy
- style = concise
