# Overview

该文档描述 `backchannel` Skill 的详细规范与扩展说明。

references/spec.md：casual_chat.backchannel 正式规范

旧资产名称：实时短反馈

# Detailed Rules

## Instructions

- 极短。
- 只表达“在听/在跟/收到”。
- 语气自然，不像系统播报。

## Description

双工或实时语音里的极短确认反馈。

## Objective

维持实时对话感，不抢占说话时间。

# Rendering Notes

## Response Contract

- max_sentences = 1

## Speech Policy

- style = realtime

# Asset Notes

如需扩展模板或示例，请放入当前 Skill 的 `assets/` 目录。

# Examples

- 在吗
- 好的
- 当路由计划选择 casual_chat.backchannel 时使用
- 当需要为当前轮回答注入 mode 级约束时使用
