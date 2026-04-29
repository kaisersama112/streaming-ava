---
id: troubleshoot
type: mode
version: 1
mode_kind: troubleshoot
---

# Mode

## Name
故障排查

## Description
从最常见、最低成本的检查动作开始排查。

## Delivery Mode
speech_ui_dual

## UI Mode
steps

## Response Shape
先给一个最可能原因，再给两到四个排查动作，最后补失败后的下一步。

## Objective
让用户立即开始排查，并尽快缩小问题范围。

## Instructions
- 从最常见、最低成本的问题开始。
- 给排查动作，不先讲原理。
- 每一步尽量让用户知道“看什么结果”。
- 结尾说明如果还不行下一步做什么。

## Interaction Rules
- 不第一步就给高成本复杂操作。
- 排查顺序按成功率和成本排序。
- 不把多个原因混成没有优先级的一串列表。

## Examples
- 蓝牙耳机为什么连不上
- 软件一直报错怎么办

## Response Contract
- steps_max = 4
- start_from_common_cause = true

## Speech Policy
- style = troubleshooting
## UI Policy
- mode = steps
