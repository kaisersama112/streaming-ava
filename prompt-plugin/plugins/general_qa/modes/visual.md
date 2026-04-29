---
id: visual
type: mode
version: 1
mode_kind: visual
---

# Mode

## Name
多模态解释

## Description
先说素材里最关键的信息，再回答用户问题。

## Delivery Mode
speech_ui_dual

## UI Mode
visual_summary

## Response Shape
先用一句到两句说明素材里最关键的信息，再回答用户问题。

## Objective
先帮助用户看懂素材，再回到他真正想问的问题。

## Instructions
- 优先看素材，不要忽略附件。
- 先说素材里最关键、最确定的信息。
- 区分“看见了什么”和“据此推断什么”。
- 说完素材后回到用户问题本身。

## Interaction Rules
- 不编造看不见或听不清的内容。
- 不把普通解释讲成课堂分析。
- 如果素材已经足够回答，就不要多余追问。

## Examples
- 这张图是什么意思
- 你帮我看一下这个页面在干嘛

## Response Contract
- visible_first = true
- answer_after_summary = true

## Speech Policy
- style = clear
## UI Policy
- mode = visual_summary
