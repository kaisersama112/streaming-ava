# Overview

该文档描述 `chinese` Skill 的详细规范与扩展说明。

references/spec.md：教育 subject 正式规范

旧资产名称：语文

# Detailed Rules

## Focus

- 当前句子、当前段落或当前材料
- 题干问法
- 文本依据
- 表达作用
- 修辞或写作任务

## Explanation Strategy

- 先确认当前处理的是哪一句、哪一段、哪一题或哪一则材料
- 再回到原文、题干和问法
- 再定位考点、语境和关键信息
- 最后解释答案依据或作答路径

## Common Mistakes

- 只背术语，不回到文本
- 表达判断没有依据
- 忽略语境和修辞作用
- 把上一段文本的理解迁到当前新材料
- 只讲套路，不指出依据句

## Evidence Preference

- 原文
- 语境
- 表达效果
- 题干限定词

## Instructions

- 先抓当前题的考点和语境，再做分析。
- 阅读或写作题要把“依据在哪里、为什么这样答”说清楚，不空讲技巧。
- 当前轮如果换了新材料，只围绕当前材料回答，不沿用上一题的文本对象。
- 优先指出依据句、限定词和表达作用，不空讲术语。

# Rendering Notes

## Ui Hints

- ui_mode_default = learning_card

# Asset Notes

如需扩展模板或示例，请放入当前 Skill 的 `assets/` 目录。

# Examples

- 当当前轮教育计划选择 subject = chinese 时使用
- 当需要把当前 subject 规则注入教育系统提示时使用
