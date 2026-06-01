# Overview

该文档描述 `compare` Skill 的详细规范与扩展说明。

references/spec.md：general_qa.compare 正式规范

旧资产名称：简短对比

# Detailed Rules

## Instructions

- 直接给倾向判断。
- 差异只保留最关键的一到两个维度。
- 优先围绕用户当前目标给建议，不做泛泛罗列。
- 条件不足时，也给保守结论口径。

## Description

对比两个选项并给选择建议。

## Objective

帮用户快速做出选择，让他知道“该怎么选”和“主要差在哪”，而不是展开成长评测。

# Rendering Notes

## Response Contract

- answer_first = true
- compare_dimensions_max = 2

## Speech Policy

- style = concise_compare

# Asset Notes

如需扩展模板或示例，请放入当前 Skill 的 `assets/` 目录。

# Examples

- 平板和学习机哪个好
- 这两个设置有什么区别
- 当路由计划选择 general_qa.compare 时使用
- 当需要为当前轮回答注入 mode 级约束时使用
