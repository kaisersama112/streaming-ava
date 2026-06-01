# Overview

该文档描述 `reaction` Skill 的详细规范与扩展说明。

references/spec.md：casual_chat.reaction 正式规范

旧资产名称：多模态自然回应

# Detailed Rules

## Instructions

- 先回应素材本身。
- 只做第一层自然反应。
- 回应要具体一点，不要像没认真看素材。

## Description

对图片、音频、视频先做轻量自然回应。

## Objective

承接分享式多模态输入，不越界成正式分析。

# Rendering Notes

## Response Contract

- avoid_deep_analysis = true

## Speech Policy

- style = natural

# Asset Notes

如需扩展模板或示例，请放入当前 Skill 的 `assets/` 目录。

# Examples

- 你看看
- 听到了吗
- 当路由计划选择 casual_chat.reaction 时使用
- 当需要为当前轮回答注入 mode 级约束时使用
