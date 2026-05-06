## 项目简介

`streaming-ava` 是一个支持多模态输入、单轮模型意图规划、实时语音输出和全双工打断的对话式应用骨架。

当前主链路：

```text
文本/语音/附件输入
-> TurnInput
-> Context Assemble
-> Router(route + plan)
-> build_turn_plan
-> responder LLM
-> speech postprocess
-> TTS / WebRTC 播放
```

---

## 当前代码结构

项目当前以 `ava/` 包为核心，采用 `application / domain / infrastructure` 分层；实时 Web 入口已经收敛到根目录 `app.py`，`realtime_server.py` 负责启动服务。

### 核心目录

- 根目录
  - `app.py`：FastAPI + WebSocket 实时交互入口，负责文本、音频、附件接入
  - `realtime_server.py`：基于 `settings.server` 启动 uvicorn
- `ava/application/`
  - `conversation.py`：turn 前准备、turn 后持久化
  - `multimodal.py`：构建 `TurnInput` 与 `MediaArtifact`
  - `routing/`：RouterService、heuristics、router message 组装
  - `orchestration/`：`router_plan` 落地、strategy 物化、responder messages 组装
  - `realtime/`：全双工 realtime session、barge-in、事件总线、turn 控制
  - `services/voice_chat.py`：CLI/单轮应用服务
  - `speech/`：数学口播后处理、LaTeX span 检测、流式 speech buffer
  - `trace.py`：结构化 trace 日志
- `ava/domain/`
  - `context/`：`TurnInput`、`ContextSnapshot`、上下文组装
  - `routing/`：`RouteDecision`、schema、置信度策略
  - `session/state.py`：`ConversationState`
  - `strategy/models.py`：PromptSelection、ResolvedPromptSpec、BranchStrategy
- `ava/infrastructure/`
  - `llm/`：主 responder、router 与可选多模态扩展 client
  - `tts/`：流式 TTS 与 REST TTS
  - `asr/`：ASR 适配与流式客户端
  - `realtime/`：WebRTC/FastRTC bridge 与兼容补丁
  - `prompts/`：PromptCenter、prompt builder、运行时 prompt 资产解析
- `prompt-plugin/`
  - Prompt 资产：`core + plugins + evals`
- `config/`
  - Pydantic 配置模型与运行配置

---

## 入口与运行方式

### 实时 Web

启动：

```bash
python realtime_server.py
```

当前真实入口：

- 启动脚本：`realtime_server.py`
- Web 应用：`app.py`
- WebSocket：`/ws/audio`

访问地址由 `config/config.yaml` 中的 `server.host` 与 `server.port` 决定。
当前仓库配置里端口是 `7002`，示例配置 `config/config.example.yaml` 仍使用 `7000`。

### CLI

当前 CLI 能力收敛在 `ava/application/services/voice_chat.py`，用于单轮对话、TTS 文件生成和本地调试。

---

## Router 与编排

### Router 输出

Router 当前不是只做粗粒度场景路由，而是一次模型调用直接输出：

- `session_scene`
- `turn_scene`
- `intent`
- `confidence`
- `should_preserve_teaching_state`
- `need_clarification`
- `plan`

其中 `plan` 会直接决定当前轮后续该落到哪个 prompt 资产：

- `education`：`module / subject / style / policy_id / primary_action / primary_scenario`
- `general_qa / casual_chat / clarify`：`mode`

这一步的关键约束是：

- 不能只看当前一句短文本
- 必须结合最近几轮原始问答、当前状态、摘要和附件
- “我不会 / 没懂 / 下一步 / 这个呢” 这类短追问，必须在 Router 这一层结合历史恢复真实对象
- 一旦模型成功返回 `plan`，后续主链不再做第二轮语义判定

### 编排链路

```text
assemble_context
-> RouterService.route_with_context
-> RouteDecision + router_plan
-> build_turn_plan
-> model_plan_builder
-> BranchStrategy
-> responder messages
```

`build_turn_plan()` 当前只做三件事：

- 读取上游已经产出的 `router_plan`
- 校验并补默认值
- 从 prompt 资产装配 `BranchStrategy`，再组 responder `messages`

它不再承担：

- scene-specific orchestrator 二次分流
- turn frame resolver
- 本地 module / subject / style selector
- 本地 mode selector

### 教育分支

教育分支当前真实链路：

```text
RouteDecision + router_plan
-> model_plan_builder
-> plugin / module / subject / style asset
-> BranchStrategy
-> responder
```

说明：

- Router 已经直接给出 `module / subject / style`
- orchestration 只做校验、补默认值和资产装配
- responder `messages` 会附最近几轮原始 Q/A；如果原始历史已经进 `messages`，system prompt 只保留短摘要
- 当前主链不再依赖本地 selector 规则来决定教育内部资产

---

## Realtime 语音链路

### 核心模块

- `app.py`
- `ava/application/realtime/session.py`
- `ava/application/realtime/barge_in.py`
- `ava/application/voice_stream.py`
- `ava/infrastructure/asr/streaming_client.py`
- `ava/infrastructure/tts/streaming_sdk.py`
- `ava/infrastructure/realtime/bridge.py`

### 数据流

```text
ASR partial/final or text submit
-> RealtimeConversationSession
-> submit_turn
-> RouterService.route_with_context
-> build_turn_plan
-> responder LLM stream
-> LatexAwareSpeechBuffer
-> StreamingVoicePipeline
-> RealtimeAudioBridge
-> 浏览器播放
```

### 当前特性

- 支持 `partial` barge-in
- 支持 `final` 强制抢占当前输出
- 支持文本输入在 assistant 说话或思考时立即打断
- 支持多模态 turn 进入 realtime 主链
- 支持中断后按配置重建播放流：`runtime.realtime_audio_rebuild_on_interrupt`
- 支持 TTS 回声过滤，避免播放内容被 ASR 误判为用户打断

### Web 入口补充说明

根目录 `app.py` 不只是 WebSocket 壳层，还负责：

- 接收文本、音频与附件输入
- 解码前端上传的 base64 附件
- 拉取并归一化 URL 附件（含 GitHub blob/raw 场景）
- 把附件与 turn 一并送入 realtime 主链

---

## 数学口播后处理

数学口播现在是 responder 输出后的独立后处理层，不再依赖 Prompt“尽量口语化”。

当前链路：

```text
Responder text
-> detect_latex_spans
-> math_oralizer
-> math_latex_oralizer
-> speech_text
-> TTS
```

### 当前文件

- `ava/application/speech/latex_span_detector.py`
- `ava/application/speech/math_ir.py`
- `ava/application/speech/math_oralizer.py`
- `ava/application/speech/math_latex_oralizer.py`
- `ava/application/speech/text_builder.py`
- `ava/application/speech/stream_buffer.py`

### 当前实现说明

- 只有 `education + math` 分支默认启用
- `math_latex_oralizer.py` 是唯一内核
- `math_oralizer.py` 只是薄适配层
- 根目录 `demo_parse_latex.py` 现在只是兼容转发入口
- trace 中会记录 oralizer 的 backend / mode / fallback 信息

---

## Prompt 资产

Prompt 根目录为 `prompt-plugin/`。

当前结构：

- `core/`：base / contracts / renderer / router
- `plugins/education/`：`plugin -> module -> subject -> style`
- `plugins/general_qa/`、`plugins/casual_chat/`、`plugins/clarify/`：`plugin -> mode`
- `evals/`：历史样例与评估数据

当前职责边界：

- Router 负责一次性选出当前轮 `route + plan`
- `prompt-plugin/` 负责承载内容资产和资产边界语义
- 运行时负责解析和装配资产，不再承担第二轮本地 selector 判定

---

## 配置与状态

- 主配置：`config/config.yaml`
- 配置模型：`config/__init__.py`
- 默认状态文件：`state/memory.json`
- 评估日志：`state/evaluation.jsonl`
- trace 日志：`state/trace.jsonl`

当前配置由 `Config` 聚合，核心块包括：

- `server`
- `openai_config`
- `voice_config`
- `asr_config`
- `runtime`
- `speech_postprocess`

其中 `runtime` 已成为 realtime 行为的主控制面，当前重点参数包括：

- `realtime_audio_rebuild_on_interrupt`
- `barge_in_partial_chars`
- `barge_in_stability_threshold`
- `barge_in_cooldown_ms`
- `echo_detection_window_seconds`
- `echo_detection_min_chars`
- `echo_detection_similarity_threshold`

推荐使用环境变量注入密钥：

- `STREAMING_AVA_OPENAI_API_KEY`
- `STREAMING_AVA_TTS_API_KEY`
- `STREAMING_AVA_ASR_API_KEY`

---

## 当前文档入口

- [docs/项目架构说明.md](/app/streaming-ava/docs/项目架构说明.md)
- [docs/项目总览.md](/app/streaming-ava/docs/项目总览.md)
- [docs/整体升级文档.md](/app/streaming-ava/docs/整体升级文档.md)
- [docs/基于大语言模型（LLM）的场景路由方案 可行性分析.md](/app/streaming-ava/docs/基于大语言模型（LLM）的场景路由方案%20可行性分析.md)
- [docs/数学口播转录接入方案.md](/app/streaming-ava/docs/数学口播转录接入方案.md)
