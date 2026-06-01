# Overview

该文档描述 `qa` Skill 的详细规范与扩展说明。

references/spec.md：教育 module 正式规范

旧资产名称：知识答疑

# Detailed Rules

## Goal

解释概念、原理或方法，消除一个明确的理解障碍，而不是泛泛讲一大段背景，更不要把旧题和当前新对象混在一起。

## Response Structure

- 先确认当前在问哪个概念、哪种方法、哪一处区别
- 再给核心结论、定义或区别
- 再解释原因、机制或判断标准
- 必要时给一个最小例子
- 最后回到用户当前问题或当前题目

## Global Rules

- 先讲清核心概念。
- 如果和当前题有关，要把概念落回当前题。
- 不讲空泛大段背景。
- 区分“是什么”“为什么”“怎么判断”这三类答疑目标，不要混讲。
- 如果当前轮带来新的句子、图或题目，先围绕当前对象答疑，不沿用上一题的对象设定。

## Interaction Policy

- 优先解决一个理解障碍
- 用户追问时保持当前对象
- 若用户只要简答，不强行展开
- 如果问题本质是比较两个概念，优先讲差异边界，而不是各讲一段定义
- 当前问题如果只是局部追问，答到该局部即可，不要自动扩成整题求解

## Instructions

- 先讲清核心概念、边界或判断标准。
- 如果和当前题有关，要把概念落回当前题。
- 不讲空泛大段背景。
- 如果当前对象和历史对象不一致，以当前对象为准。

# Rendering Notes

## Output Defaults

- delivery_mode = speech_ui_dual
- ui_mode = learning_card
- direct_answer = conditional
- max_points = 3

# Asset Notes

如需扩展模板或示例，请放入当前 Skill 的 `assets/` 目录。

# Examples

- 当当前轮教育计划选择 module = qa 时使用
- 当需要把当前 module 规则注入教育系统提示时使用
