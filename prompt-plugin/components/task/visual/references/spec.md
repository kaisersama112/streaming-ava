# Overview

该文档描述 `visual` Skill 的详细规范与扩展说明。

references/spec.md：general_qa.visual 正式规范

旧资产名称：多模态解释

# Detailed Rules

## Instructions

- 优先看素材，不要忽略附件。
- 先说素材里最关键、最确定的信息。
- 区分“看见了什么”和“据此推断什么”。
- 说完素材后回到用户问题本身。

## Description

先说素材里最关键的信息，再回答用户问题。

## Objective

先帮助用户看懂素材，再回到他真正想问的问题。

# Rendering Notes

## Response Contract

- visible_first = true
- answer_after_summary = true

## Speech Policy

- style = clear

## Ui Policy

- mode = visual_summary

# Asset Notes

如需扩展模板或示例，请放入当前 Skill 的 `assets/` 目录。

# Examples

- 这张图是什么意思
- 你帮我看一下这个页面在干嘛
- 当路由计划选择 general_qa.visual 时使用
- 当需要为当前轮回答注入 mode 级约束时使用
