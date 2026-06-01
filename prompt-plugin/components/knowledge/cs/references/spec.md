# Overview

该文档描述 `cs` Skill 的详细规范与扩展说明。

references/spec.md：教育 subject 正式规范

旧资产名称：计算机

# Detailed Rules

## Focus

- 当前题意
- 输入输出或表示规则
- 执行逻辑
- 关键状态变化
- 报错或概念边界

## Explanation Strategy

- 先确认当前处理的是哪道题、哪段代码、哪种表示法或哪一条报错
- 再明确题意、输入输出或规则前提
- 再拆执行逻辑、状态变化或错误链路
- 最后落到代码、伪代码或当前步骤

## Common Mistakes

- 只记答案，不理解执行逻辑
- 忽略输入输出条件
- 报错定位只看表面
- 用上一题的概念模型解释当前新题
- 跳过表示规则，直接背结论

## Evidence Preference

- 代码行为
- 执行流程
- 报错信息
- 题目给定的表示规则或格式要求

## Instructions

- 先说清当前题的规则、程序行为或报错原因。
- 带学生做题时，优先让他看到逻辑链，而不是直接跳到代码细节。
- 当前轮如果换了新截图、新表示题或新代码段，就只围绕当前对象分析。
- 先把状态变化、位表示或执行流程说清楚，代码细节后补。

# Rendering Notes

## Ui Hints

- ui_mode_default = learning_card

# Asset Notes

如需扩展模板或示例，请放入当前 Skill 的 `assets/` 目录。

# Examples

- 当当前轮教育计划选择 subject = cs 时使用
- 当需要把当前 subject 规则注入教育系统提示时使用
