# Overview

该文档描述 `troubleshoot` Skill 的详细规范与扩展说明。

references/spec.md：general_qa.troubleshoot 正式规范

旧资产名称：故障排查

# Detailed Rules

## Instructions

- 从最常见、最低成本的问题开始。
- 给排查动作，不先讲原理。
- 每一步尽量让用户知道“看什么结果”。
- 结尾说明如果还不行下一步做什么。

## Description

从最常见、最低成本的检查动作开始排查。

## Objective

让用户立即开始排查，并尽快缩小问题范围。

# Rendering Notes

## Response Contract

- steps_max = 4
- start_from_common_cause = true

## Speech Policy

- style = troubleshooting

## Ui Policy

- mode = steps

# Asset Notes

如需扩展模板或示例，请放入当前 Skill 的 `assets/` 目录。

# Examples

- 蓝牙耳机为什么连不上
- 软件一直报错怎么办
- 当路由计划选择 general_qa.troubleshoot 时使用
- 当需要为当前轮回答注入 mode 级约束时使用
