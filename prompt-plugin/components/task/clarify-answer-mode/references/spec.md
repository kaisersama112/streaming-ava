# Overview

该文档描述 `clarify-answer-mode` Skill 的详细规范与扩展说明。

references/spec.md：clarify.answer_mode 正式规范

旧资产名称：回答方式

# Detailed Rules

## Instructions

- 只澄清回答深度。
- 用自然口语问法。
- 问句要让用户一听就知道怎么接。

## Description

用户没说清要详细步骤还是快速结论。

## Objective

先对齐回答深度，避免答偏。

# Rendering Notes

## Response Contract

- single_question_only = true

## Speech Policy

- style = brief

# Asset Notes

如需扩展模板或示例，请放入当前 Skill 的 `assets/` 目录。

# Examples

- 你讲一下
- 帮我看看怎么弄
- 当路由计划选择 clarify.answer_mode 时使用
- 当需要为当前轮回答注入 mode 级约束时使用
