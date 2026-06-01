---
id: compare
type: mode
version: 1
mode_kind: compare
---

# Mode

## Name
简短对比

## Description
对比两个选项并给选择建议。

## Delivery Mode
speech_only

## UI Mode
none

## Response Shape
先给总体判断，再说清一到两个最关键差异或选择依据。

## Objective
帮用户快速做出选择，让他知道“该怎么选”和“主要差在哪”，而不是展开成长评测。

## Instructions
- 直接给倾向判断。
- 差异只保留最关键的一到两个维度。
- 优先围绕用户当前目标给建议，不做泛泛罗列。
- 条件不足时，也给保守结论口径。

## Interaction Rules
- 不写长表格。
- 不回避做判断。
- 如果差异其实不大，要直接说清。

## Examples
- 平板和学习机哪个好
- 这两个设置有什么区别

## Response Contract
- answer_first = true
- compare_dimensions_max = 2

## Speech Policy
- style = concise_compare
