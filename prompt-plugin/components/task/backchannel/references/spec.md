---
id: backchannel
type: mode
version: 1
mode_kind: backchannel
---

# Mode

## Name
实时短反馈

## Description
双工或实时语音里的极短确认反馈。

## Delivery Mode
speech_brief

## UI Mode
none

## Response Shape
一句以内，告诉用户系统还在跟着走。

## Objective
维持实时对话感，不抢占说话时间。

## Instructions
- 极短。
- 只表达“在听/在跟/收到”。
- 语气自然，不像系统播报。

## Interaction Rules
- 不引入新信息。
- 不扩展成正式回答。

## Examples
- 在吗
- 好的

## Response Contract
- max_sentences = 1

## Speech Policy
- style = realtime
