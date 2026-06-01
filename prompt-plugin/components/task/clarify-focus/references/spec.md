# Overview

该文档描述 `clarify-focus` Skill 的详细规范与扩展说明。

references/spec.md：clarify.focus 正式规范

旧资产名称：素材焦点

# Detailed Rules

## Instructions

- 只问一个焦点问题。
- 把问题缩到最可能的关注点。
- 能结合当前素材内容缩小范围时，就不要空问“你想看什么”。

## Description

已经给了图片、音频或视频，但没说清想看哪个重点。

## Objective

让下一轮能够聚焦一个清晰的分析点。

# Rendering Notes

## Response Contract

- single_question_only = true

## Speech Policy

- style = brief

# Asset Notes

如需扩展模板或示例，请放入当前 Skill 的 `assets/` 目录。

# Examples

- 帮我看一下
- 讲讲这个
- 当路由计划选择 clarify.focus 时使用
- 当需要为当前轮回答注入 mode 级约束时使用
