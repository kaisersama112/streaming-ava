# Realtime

`ava/application/realtime/` 负责全双工实时会话。

它把这些东西串成一条可打断的实时链路：

- ASR partial / final
- 文本与附件型 submit
- 当前轮抢占与 barge-in
- responder 流式输出
- 流式 TTS
- WebRTC 播放事件与状态同步

## 核心职责

- 管理当前 active turn
- 处理 speaking / thinking 阶段的用户抢占
- 把一轮 realtime turn 从输入一路推进到完成
- 发布前端可消费的 realtime events

## 当前主链

```text
ASR partial/final or text submit
-> RealtimeConversationSession
-> submit_turn
-> router.route
-> build_turn_plan
-> llm_client.chat_stream
-> LatexAwareSpeechBuffer
-> StreamingVoicePipeline
-> RealtimeAudioBridge
-> complete_realtime_turn
```

## 关键文件

- `session.py`
  - realtime 主控制器
- `barge_in.py`
  - partial 级打断判定
- `events.py`
  - 事件类型与总线
- `turn.py`
  - turn 状态和控制对象

## 当前行为约定

- `partial` 命中 barge-in 时会立即抢占当前 turn
- `final` 到来时即使 partial 没抢占，也会在新 turn 开始前 preempt 当前输出
- 文本 submit 和附件 submit 也会先抢占当前 speaking/thinking turn
- realtime 热路径已避免 router 重复 assemble 同一份上下文
- state 的 summary 刷新和 save 统一收口在 `complete_realtime_turn()`

## 不在这一层做的事

- 不定义 `ConversationState` 的持久化模型
- 不直接实现 OpenAI / TTS / ASR SDK
- 不直接管理 Prompt 资产

## 依赖关系

- 上游入口通常来自 [ava/realtime_web/app.py](/app/streaming-ava/ava/realtime_web/app.py)
- 依赖 [routing/README.md](/app/streaming-ava/ava/application/routing/README.md) 和 [orchestration/README.md](/app/streaming-ava/ava/application/orchestration/README.md)
- 依赖 [speech/README.md](/app/streaming-ava/ava/application/speech/README.md) 做数学口播后处理
