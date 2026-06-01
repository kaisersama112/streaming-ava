# Overview

该文档描述 `clarify-missing-reference` Skill 的详细规范与扩展说明。

references/spec.md：clarify.missing_reference 正式规范

旧资产名称：指代不清

# Detailed Rules

## Instructions

- 聚焦“这个”到底指什么。
- 问句缩到最小范围。
- 优先结合最近对象或附件去问，不要像没看上下文。

## Description

当前轮的“这个/那个/它”没有明确指向。

## Objective

先确认当前最关键的引用对象，避免系统答偏。

# Rendering Notes

## Response Contract

- single_question_only = true

## Speech Policy

- style = brief

# Asset Notes

如需扩展模板或示例，请放入当前 Skill 的 `assets/` 目录。

# Examples

- 这个我不懂
- 你帮我看一下那个
- 当路由计划选择 clarify.missing_reference 时使用
- 当需要为当前轮回答注入 mode 级约束时使用
