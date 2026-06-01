# Overview

该文档描述 `clarify-missing-material` Skill 的详细规范与扩展说明。

references/spec.md：clarify.missing_material 正式规范

旧资产名称：素材缺失

# Detailed Rules

## Instructions

- 直接指出缺哪类素材。
- 只问一个补素材问题。
- 如果缺的是题面、截图、音频或视频，要说得具体可执行。

## Description

用户提到了题目、图片、音频或视频，但当前轮没给素材。

## Objective

补齐当前回答真正缺失的附件或题面。

# Rendering Notes

## Response Contract

- single_question_only = true

## Speech Policy

- style = brief

# Asset Notes

如需扩展模板或示例，请放入当前 Skill 的 `assets/` 目录。

# Examples

- 帮我看看这道题
- 这个视频帮我讲一下
- 当路由计划选择 clarify.missing_material 时使用
- 当需要为当前轮回答注入 mode 级约束时使用
