# Services

`ava/application/services/` 放面向入口层的应用服务。

这些服务通常不关心 WebSocket、FastAPI 或 CLI 参数解析细节，而是提供“把一次业务动作跑通”的高层接口。

## 当前文件

- `voice_chat.py`
  - 单轮对话服务
  - 负责：state、router、turn plan、reply、speech_text、TTS 文件生成
- `voice_interaction.py`
  - 语音交互相关应用服务
  - 主要用于语音侧流程封装与集成

## 与其他 application 子模块区别

- `routing/` 负责粗路由
- `orchestration/` 负责 turn plan
- `realtime/` 负责全双工实时会话
- `services/` 负责把这些能力组织成“可直接被入口调用”的服务对象

## 典型调用

### `VoiceChatService`

```text
user_text
-> build_turn_input
-> prepare_state_for_turn
-> router.route
-> build_turn_plan
-> llm reply
-> build_speech_text
-> persist_turn
-> TTS synthesize
```

## 文档约束

这一层只描述“服务对象如何组织主流程”，不重复详细解释：

- Router 内部 prompt 组装
- Realtime turn 状态机
- 数学口播算法细节

这些分别见：

- [routing/README.md](/app/streaming-ava/ava/application/routing/README.md)
- [realtime/README.md](/app/streaming-ava/ava/application/realtime/README.md)
- [speech/README.md](/app/streaming-ava/ava/application/speech/README.md)
