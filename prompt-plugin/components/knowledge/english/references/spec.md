# Overview

该文档描述 `english` Skill 的详细规范与扩展说明。

references/spec.md：教育 subject 正式规范

旧资产名称：英语

# Detailed Rules

## Focus

- 当前句子或当前空
- 语法与句法
- 语义与语境
- 选项边界
- 干扰项排除

## Explanation Strategy

- 先确认当前处理的是哪一句、哪个空、哪个划线部分或哪个选项
- 再重建题干和语境
- 再定位语言点、句法结构或语义逻辑
- 最后解释为什么选这个答案，以及其他选项为什么不合适

## Common Mistakes

- 只记规则，不看语境
- 混淆近义表达
- 只翻译，不分析结构
- 用上一题的语法点去解释当前新句子
- 没把选项放回原句就直接判断

## Evidence Preference

- 原句
- 语境
- 规则
- 选项替换后的句子效果

## Instructions

- 先定位当前句子的语言点，再解释为什么选这个答案。
- 不只说规则名，要把规则落回当前句子和当前选项。
- 如果当前轮是新题图，就只分析当前句子，不把上一题内容一并解释。
- 讲选择题时，优先说明正确项为什么成立，再点干扰项为什么不成立。

# Rendering Notes

## Ui Hints

- ui_mode_default = learning_card

# Asset Notes

如需扩展模板或示例，请放入当前 Skill 的 `assets/` 目录。

# Examples

- 当当前轮教育计划选择 subject = english 时使用
- 当需要把当前 subject 规则注入教育系统提示时使用
