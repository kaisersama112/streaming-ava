# Overview

该文档描述 `clarify-subject` Skill 的详细规范与扩展说明。

references/spec.md：clarify.subject 正式规范

旧资产名称：学科任务边界

# Detailed Rules

## Instructions

- 只澄清一个最关键边界。
- 问句保持自然。
- 能把边界收成最少两个方向时，就不要列太多选项。

## Description

当前轮可能跨学科或跨任务，先问清主边界。

## Objective

避免系统在错误领域里展开回答。

# Rendering Notes

## Response Contract

- single_question_only = true

## Speech Policy

- style = brief

# Asset Notes

如需扩展模板或示例，请放入当前 Skill 的 `assets/` 目录。

# Examples

- 你是想问数学题，还是物理实验这个现象
- 当路由计划选择 clarify.subject 时使用
- 当需要为当前轮回答注入 mode 级约束时使用
