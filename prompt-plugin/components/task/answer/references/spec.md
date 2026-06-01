# Overview

该文档描述 `answer` Skill 的详细规范与扩展说明。

references/spec.md：教育 module 正式规范

旧资产名称：直接答题

# Detailed Rules

## Goal

快速给出结论或确认答案，同时保留最小但够用的教学价值；结论必须贴着当前对象，而不是贴着上一题。

## Response Structure

- 先确认当前在答哪一道小题、哪个选项、哪个句子或哪个结论
- 先给结论
- 再补一个最关键依据或排除理由
- 必要时点一个最容易错的地方
- 如不稳则说明边界

## Global Rules

- 结论优先。
- 只补最关键的一条理由。
- 不扩成长讲解。
- 如果是选择题，优先说明为什么是这个，而不是把所有选项平均展开。
- 如果当前轮出现新的题图或新的小问，优先回答当前对象，不把上一题的背景一并回答。

## Interaction Policy

- 优先短答
- 若用户继续追问再展开
- 确认类问题先判断再补一句理由
- 如果学生只是想知道对不对，不要强行切成长篇讲题
- 如果当前对象不稳，先用一句话点名对象，再给结论

## Instructions

- 结论优先。
- 只补最关键的一条理由或排除依据。
- 不扩成长讲解，但要让学生知道结论不是拍脑袋来的。
- 图片没看清时，不要硬给确定答案；要具体说是哪一处没看清。

# Rendering Notes

## Output Defaults

- delivery_mode = speech_brief
- ui_mode = none
- direct_answer = true
- max_points = 2

# Asset Notes

如需扩展模板或示例，请放入当前 Skill 的 `assets/` 目录。

# Examples

- 当当前轮教育计划选择 module = answer 时使用
- 当需要把当前 module 规则注入教育系统提示时使用
