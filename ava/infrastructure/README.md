# Infrastructure Layer

`ava/infrastructure/` 放外部系统适配与运行时环境桥接。

它回答的是：

- 怎么调 OpenAI-compatible LLM
- 怎么调 GLM 慢路径
- 怎么调流式 / 非流式 TTS
- 怎么调 ASR
- 怎么把音频送进 WebRTC 播放桥
- 怎么加载和渲染 Prompt 资产

## 当前子模块

- `llm/`
  - 主 responder 与 router 的 OpenAI-compatible client
  - 教育慢路径的 GLM client
- `tts/`
  - 流式 TTS SDK
  - 非流式 TTS REST 调用
- `asr/`
  - ASR 识别与流式客户端
- `realtime/`
  - bridge / patch / player
- `prompts/`
  - PromptCenter、runtime、prompt builder
- `audio/`
  - 本地播放辅助

## 当前设计边界

这一层负责：

- 与具体 SDK / HTTP API 交互
- 做协议兼容、错误归一化、播放器桥接
- 读取 Prompt markdown / yaml 资产

这一层不负责：

- 决定 turn_scene
- 选择教育 skill
- 持久化会话状态
- 决定数学口播是否启用

## 关键文件

### LLM

- [llm/client.py](/app/streaming-ava/ava/infrastructure/llm/client.py)
- [llm/bigmodel_client.py](/app/streaming-ava/ava/infrastructure/llm/bigmodel_client.py)

### TTS

- [tts/streaming_sdk.py](/app/streaming-ava/ava/infrastructure/tts/streaming_sdk.py)
- [tts/rest_client.py](/app/streaming-ava/ava/infrastructure/tts/rest_client.py)

### Realtime

- [realtime/bridge.py](/app/streaming-ava/ava/infrastructure/realtime/bridge.py)
- [realtime/patch.py](/app/streaming-ava/ava/infrastructure/realtime/patch.py)
- [realtime/player.py](/app/streaming-ava/ava/infrastructure/realtime/player.py)

### Prompts

- [prompts/config.py](/app/streaming-ava/ava/infrastructure/prompts/config.py)
- [prompts/loader.py](/app/streaming-ava/ava/infrastructure/prompts/loader.py)
- [prompts/runtime.py](/app/streaming-ava/ava/infrastructure/prompts/runtime.py)
- [prompts/prompt_builder.py](/app/streaming-ava/ava/infrastructure/prompts/prompt_builder.py)

## 与其他层关系

- 被 [ava/application/README.md](/app/streaming-ava/ava/application/README.md) 调用
- 读取 `config/` 和 `prompt-plugin/` 资源
- 不承载业务路由和编排规则
