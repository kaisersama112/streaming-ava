# Overview

该文档描述 `howto` Skill 的详细规范与扩展说明。

references/spec.md：general_qa.howto 正式规范

旧资产名称：短步骤指导

# Detailed Rules

## Instructions

- 步骤按顺序写清楚。
- 每一步只保留一个核心动作。
- 优先给动作，不讲原理。
- 如果有明显起点或入口，先说从哪里开始。

## Description

普通操作问题，输出最短可执行步骤。

## Objective

给用户一套最短可执行路径，让他马上能开始操作。

# Rendering Notes

## Response Contract

- steps_min = 2
- steps_max = 4

## Speech Policy

- style = step_short

## Ui Policy

- mode = steps

# Asset Notes

如需扩展模板或示例，请放入当前 Skill 的 `assets/` 目录。

# Examples

- 怎么连接蓝牙耳机
- 这个软件怎么导出 PDF
- 当路由计划选择 general_qa.howto 时使用
- 当需要为当前轮回答注入 mode 级约束时使用
