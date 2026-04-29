---
id: scene
type: mode
version: 1
mode_kind: scene
---

# Mode

## Name
回答场景

## Description
当前轮不确定是老师式讲解还是普通回答。

## Delivery Mode
speech_brief

## UI Mode
none

## Response Shape
只问一句，确认想要老师式讲解还是直接回答。

## Objective
先把回答场景对齐，避免整条分支走偏。

## Instructions
- 优先澄清回答方式，不问内容细节。
- 问法自然简短，让用户能直接选“直接答”还是“像老师一样讲”。

## Interaction Rules
- 不给过多选项。
- 不把场景澄清扩展成分类说明。

## Examples
- 你是直接答，还是像老师一样讲

## Response Contract
- single_question_only = true

## Speech Policy
- style = brief
