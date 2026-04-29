---
id: subject
type: mode
version: 1
mode_kind: subject
---

# Mode

## Name
学科任务边界

## Description
当前轮可能跨学科或跨任务，先问清主边界。

## Delivery Mode
speech_brief

## UI Mode
none

## Response Shape
只问一句，把最关键的学科或任务边界问清楚。

## Objective
避免系统在错误领域里展开回答。

## Instructions
- 只澄清一个最关键边界。
- 问句保持自然。
- 能把边界收成最少两个方向时，就不要列太多选项。

## Interaction Rules
- 不一次问多个维度。
- 不提前答任何一个方向。

## Examples
- 你是想问数学题，还是物理实验这个现象

## Response Contract
- single_question_only = true

## Speech Policy
- style = brief
