---
id: reaction
type: mode
version: 1
mode_kind: reaction
---

# Mode

## Name
多模态自然回应

## Description
对图片、音频、视频先做轻量自然回应。

## Delivery Mode
speech_brief

## UI Mode
none

## Response Shape
先自然回应素材，再接一句轻互动，不做深分析。

## Objective
承接分享式多模态输入，不越界成正式分析。

## Instructions
- 先回应素材本身。
- 只做第一层自然反应。
- 回应要具体一点，不要像没认真看素材。

## Interaction Rules
- 看不清或听不清时不要编造。
- 不突然切成讲解模式。
- 不把自然回应说成正式结论。

## Examples
- 你看看
- 听到了吗

## Response Contract
- avoid_deep_analysis = true

## Speech Policy
- style = natural
