# Overview

该文档描述 `confirm` Skill 的详细规范与扩展说明。

references/spec.md：general_qa.confirm 正式规范

旧资产名称：快速确认

# Detailed Rules

## Instructions

- 先明确 yes/no 或结论。
- 再补一句最必要的依据或成立条件。
- 不能确认时，明确缺什么条件。

## Description

用户只想确认对错或可行性。

## Objective

用一个极短回合完成确认，不拖成长解释。

# Rendering Notes

## Response Contract

- answer_first = true
- max_sentences = 2

## Speech Policy

- style = brief

# Asset Notes

如需扩展模板或示例，请放入当前 Skill 的 `assets/` 目录。

# Examples

- 我这样理解对吗
- 这样设置可以吗
- 当路由计划选择 general_qa.confirm 时使用
- 当需要为当前轮回答注入 mode 级约束时使用
