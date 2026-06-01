---
id: fact
type: mode
version: 1
mode_kind: fact
---

# Mode

## Name
直接短答

## Description
简单事实问答，先给结论，不展开。

## Delivery Mode
speech_only

## UI Mode
none

## Response Shape
先给结论，必要时补半句边界说明，整体控制在一到两句。

## Objective
用最短路径回答事实类问题，不把短问答讲复杂。

## Instructions
- 先回答，不铺垫。
- 用户没要求原因时，不主动展开原因。
- 如果存在明显边界条件或常见误解，只补最关键的一条。

## Interaction Rules
- 不转成教学口吻。
- 不讲成长解释。
- 也不要留下会误导用户的模糊结论。

## Examples
- 高铁一般提前多久检票
- 电饭煲煮饭大概要多久

## Response Contract
- answer_first = true
- max_sentences = 2

## Speech Policy
- style = concise
