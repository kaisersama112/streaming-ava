# Overview

该文档描述 `reasoned` Skill 的详细规范与扩展说明。

references/spec.md：general_qa.reasoned 正式规范

旧资产名称：结论加原因

# Detailed Rules

## Instructions

- 结论优先。
- 原因只说最关键的一层。
- 必要时补一个最关键的前提或边界。
- 不引入多个平行原因。

## Description

需要一句解释的普通问答。

## Objective

先解决“是什么/会不会”，再用最短理由满足解释需求。

# Rendering Notes

## Response Contract

- answer_first = true
- reasons_max = 1

## Speech Policy

- style = concise

# Asset Notes

如需扩展模板或示例，请放入当前 Skill 的 `assets/` 目录。

# Examples

- 为什么手机会发烫
- 为什么图片发不出去
- 当路由计划选择 general_qa.reasoned 时使用
- 当需要为当前轮回答注入 mode 级约束时使用
