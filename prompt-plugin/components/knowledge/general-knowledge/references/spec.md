# Overview

该文档描述 `general-knowledge` Skill 的详细规范与扩展说明。

references/spec.md：教育 subject 正式规范

旧资产名称：通用教育

# Detailed Rules

## Focus

- 题意重建
- 当前对象
- 关键条件
- 当前卡点

## Explanation Strategy

- 先确认当前到底在处理哪个对象
- 再抓关键条件、关键关系或判断标准
- 最后推进下一步

## Common Mistakes

- 对象没重建清楚就开始解释
- 忽略用户当前卡点
- 给了泛泛答案没有落回问题
- 把旧历史里的对象误当成当前对象

## Evidence Preference

- 题意重建
- 当前附件或当前文本
- 关键条件
- 当前对象
- 最稳妥解释

## Instructions

- 当学科不确定时，先准确重建当前对象，再给最稳的解释或引导。
- 当前轮如果带来新附件或新题干，以当前对象为准，不从旧历史里强行补另一道题。
- 不因为学科不确定就泛讲，要始终落回当前题、当前对象和下一步。

# Rendering Notes

## Ui Hints

- ui_mode_default = learning_card

# Asset Notes

如需扩展模板或示例，请放入当前 Skill 的 `assets/` 目录。

# Examples

- 当当前轮教育计划选择 subject = general 时使用
- 当需要把当前 subject 规则注入教育系统提示时使用
