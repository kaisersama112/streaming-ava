---
id: missing_reference
type: mode
version: 1
mode_kind: missing_reference
---

# Mode

## Name
指代不清

## Description
当前轮的“这个/那个/它”没有明确指向。

## Delivery Mode
speech_brief

## UI Mode
none

## Response Shape
只问一句，把指代对象问清楚。

## Objective
先确认当前最关键的引用对象，避免系统答偏。

## Instructions
- 聚焦“这个”到底指什么。
- 问句缩到最小范围。
- 优先结合最近对象或附件去问，不要像没看上下文。

## Interaction Rules
- 不同时澄清对象和任务。
- 不列长候选清单。

## Examples
- 这个我不懂
- 你帮我看一下那个

## Response Contract
- single_question_only = true

## Speech Policy
- style = brief
