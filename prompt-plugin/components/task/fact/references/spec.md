# Overview

该文档描述 `fact` Skill 的详细规范与扩展说明。

references/spec.md：general_qa.fact 正式规范

旧资产名称：直接短答

# Detailed Rules

## Instructions

- 先回答，不铺垫。
- 用户没要求原因时，不主动展开原因。
- 如果存在明显边界条件或常见误解，只补最关键的一条。

## Description

简单事实问答，先给结论，不展开。

## Objective

用最短路径回答事实类问题，不把短问答讲复杂。

# Rendering Notes

## Response Contract

- answer_first = true
- max_sentences = 2

## Speech Policy

- style = concise

# Asset Notes

如需扩展模板或示例，请放入当前 Skill 的 `assets/` 目录。

# Examples

- 高铁一般提前多久检票
- 电饭煲煮饭大概要多久
- 当路由计划选择 general_qa.fact 时使用
- 当需要为当前轮回答注入 mode 级约束时使用
