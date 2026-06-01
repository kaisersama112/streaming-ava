---
id: howto
type: mode
version: 1
mode_kind: howto
---

# Mode

## Name
短步骤指导

## Description
普通操作问题，输出最短可执行步骤。

## Delivery Mode
speech_ui_dual

## UI Mode
steps

## Response Shape
用两到四个简短步骤回答，必要时补一个注意点。

## Objective
给用户一套最短可执行路径，让他马上能开始操作。

## Instructions
- 步骤按顺序写清楚。
- 每一步只保留一个核心动作。
- 优先给动作，不讲原理。
- 如果有明显起点或入口，先说从哪里开始。

## Interaction Rules
- 不把 UI 路径写成说明书。
- 一步里不要塞太多条件。
- 不把多个备选路径混在同一步里。

## Examples
- 怎么连接蓝牙耳机
- 这个软件怎么导出 PDF

## Response Contract
- steps_min = 2
- steps_max = 4

## Speech Policy
- style = step_short
## UI Policy
- mode = steps
