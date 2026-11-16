# streaming-ava

实时语音和多模态对话的后端，接前端的 PCM 音频流、文本和附件，走完识别、路由、生成、语音合成再推回前端。目前主要用在教育场景（解题、批改、讲解、学情评估），也跑通用问答。

一轮对话分两步：`RouterService` 判断场景和意图，给出结构化的 `TurnPlan`；`InferenceRuntime` 拿这份计划生成回答，需要时由 Manager 编排技能子 Agent。路由阶段不产生答案，两阶段靠 `TurnPlan` 衔接。

## 跑起来

Python 3.11+。

```bash
pip install -r requirements.txt
python realtime_server.py
```

服务在 7002 端口，浏览器打开 http://127.0.0.1:7002/ 是演示 / 调试页，里面带一个路由测试面板。启动前要先注入密钥，见「配置」。

端云协同路由默认关闭，走云侧模型。要启用本地小模型，先单独起端侧服务，再改 `intent_config.provider`：

```bash
python edge_router/serve_local.py --threads 12 --port 8080
```

跑测试：

```bash
python -m pytest tests -q
```

## 请求链路

文本从 `/ws/audio` 的 JSON `type:"text"` 进来（可带 attachments），语音走同一连接的 PCM 二进制帧，经 ASR 的 partial/final 后汇入同一条路径。附件在 turn intake 时由 `ensure_visual_analysis` 生成视觉摘要并缓存，路由和主干共用，不重复做视觉推理。

```text
Browser / Web Client (static/)
  ├─ 文本输入 / PCM 音频流 / 附件（图片·音频·文件）
  └─ 路由能力测试面板（意图识别 / 分类 / 规划）
        │
        ▼
FastAPI 入口 (app.py)
  ├─ HTTP:  /health  /api/router/{test,edge,contract}
  ├─ WS:    /ws/audio?session_id=...
  └─ 静态前端挂载 /static
        │
        ▼
RealtimeConversationSession (ava/pipeline/streaming/session.py)
  ├─ ASR partial/final 接入、turn 生命周期、barge-in 打断、事件总线
  └─ 附件 intake：ensure_visual_analysis（视觉摘要缓存）
        │
        ▼
ContextCompiler (ava/multi_turn_context_builder/compiler.py)
  ├─ 编译 system / developer runtime / history / user input
  ├─ 技能插件注入、运行时状态注入、历史裁剪、多模态拼装
  └─ 产出 router payload 与 responder payload（instructions + input）
        │
        ▼
RouterService (ava/router_selector/service.py)
  ├─ route(): 端侧小模型优先 → 云侧兜底（edge_cloud.py）
  ├─ RouteDecision 解析 + 决策策略归一（policy）
  ├─ education_plan / education_resolver / strategy_builder：plan → BranchStrategy + PromptPackage
  └─ prepare_turn(): 路由 + 并行预取 responder 上下文 → PreparedTurn(route_result, turn_plan)
        │
        ▼
InferenceRuntime (ava/inference_runtime/service.py)
  ├─ 消费 TurnPlan（PromptPackage + payload）
  ├─ 选择执行路径：直接 LLM / Agents SDK
  └─ Manager 编排 (ava/intent/orchestrator.py)
        ├─ planner: Router plan → 子 Agent 编排计划（串行/并行/条件分支）
        ├─ skills: 解题 solve / 批改 check / 讲解 explain / 学情评估 assess
        ├─ protocol: task.assign/result/error · state.patch · control.cancel 信封
        └─ 状态白名单写入 (ava/domain/conversation/state_patch.py)
        │
        ▼
LLMModelExecutor (ava/llm_model_executor/service.py + agent_backend.py)
  ├─ OpenAI Responses 执行（conversation_id / previous_response_id 连续对话）
  └─ Agents SDK 工具执行后端
        │
        ▼
Speech Postprocess (ava/pipeline/speech/)
  └─ LaTeX span 检测、数学口语化、流式缓冲分段
        ▼
TTS Provider (ava/capabilities/tts/) → Realtime Audio Bridge (ava/interfaces/websocket/) → 前端播放
        │
        └─ 全程：Trace / Evaluation (ava/core/tracing.py + ava/pipeline/output/)
```

`strategy_builder` 把抽象 plan 物化成 branch/module/subject/style/delivery/ui 和 responder messages，教育分支再经 `education_resolver` 映射成教学策略。回答默认直接 LLM 流式生成；启用 Agents SDK 且分支、模块在允许名单内时才走 Agent，多模态上下文复杂时优先回退直接 LLM。生成结果先过 LaTeX 检测、数学口语化和流式分段，让公式适合朗读，再送 TTS。

## 实现要点

### 路由

在 `ava/router_selector/`，`ava/routing/` 只保留旧导入路径，新代码不要依赖。输入是当前用户消息、最近几轮原始问答、最近结构化状态和附件理解，一次输出 `RouteDecision`（`session_scene`、`turn_scene`、`intent`、`confidence`、`need_clarification`、`should_preserve_teaching_state`）和结构化 plan；`prepare_turn()` 在路由的同时并行预取 responder 上下文，返回 `PreparedTurn(route_result, turn_plan)`。路由之后本地不再重复做规则路由。

`edge_cloud.py` 负责端侧请求改写、路由指纹 TTL 缓存和云侧兜底。端云降级的开关与阈值见「端侧小模型」。

### 回答与编排

`ava/inference_runtime/` 消费 `TurnPlan` 并选回复路径，`ava/llm_model_executor/` 执行模型调用（OpenAI Responses，用 `conversation_id` / `previous_response_id` 保持连续对话），`ava/intent/` 是 Manager 与技能子 Agent 的编排。Manager 按 Router 的 plan 调度 solve / check / explain / assess，支持串行、并行和条件分支；编排器用注册谓词做分支，不 eval 模型输出，并支持 `stop_event` 取消。子 Agent 之间用 `task.assign/result/error`、`state.patch`、`control.cancel` 信封通信（`correlation_id` + `seq`），技能的系统指令来自 `prompt-plugin/components/task/*`。

会话状态的写入只有一处：`ava/domain/conversation/state_patch.py` 的白名单机制。子 Agent 只提交文本和 patch 建议，`session_scene`、`turn_records`、`memory` 不在白名单内；patch 的应用和拒绝都会落 trace。

### 上下文与状态

`ava/multi_turn_context_builder/compiler.py` 是唯一的上下文编译入口，输出固定为 `{instructions, input[]}`：`input` 按对话顺序排列，user 块用 `input_text/input_image`，assistant 块用 `output_text`。静态策略放在 `prompt-plugin/`（按 core / components / capabilities / TEMPLATES 组织，Skill 模板是 `SKILL.md` + `references/spec.md` + `assets/`），运行时状态由 ContextCompiler 注入，教学规则不硬编码在代码里。

会话事实源是 `ConversationState` 的 `turn_records`；长期记忆和教育态在 `SessionMemory`（`state.memory.*`），含用户事实槽位、近期主题、多模态摘要和附件分析缓存。`ava/domain/multimodal/continuity.py` 管视觉引用的继承：当前轮出现新图片或音视频 artifact 就切断旧引用，纯文字追问则继承最近视觉摘要（带来源 `turn_id`）。

### 实时与埋点

ASR partial 驱动、token 级流式返回、边生成边播、barge-in 打断（按 partial 字数 / 稳定度 / 冷却检测）、未完成 turn 的上下文保留；音频桥与播放器分离，另有 echo detection 和播放时序打点（首 token / 首音频 / 首播延迟）。`ava/core/tracing.py` 的 `trace_event` 覆盖路由决策、模型选择、上下文快照、Agent 事件和状态 patch，`ava/pipeline/output/` 把评估标签写进 `state/evaluation.jsonl`。

## 代码结构

```text
streaming-ava/
├─ app.py / realtime_server.py     # FastAPI 应用工厂 / 本地启动入口（uvicorn，含 Windows 代理 bootstrap）
├─ requirements.txt / pyproject.toml / poetry.lock
├─ ava/                            # 主代码
├─ configs/                        # 主配置 + 各 provider 配置 + settings 加载/校验/覆盖
├─ prompt-plugin/                  # Prompt / Skill 资产
├─ edge_router/                    # 端侧小模型：下载/剪枝/量化/部署/评测/微调
├─ static/                         # 演示 / 调试前端（模块化 JS，含路由测试面板）
├─ scripts/                        # 早期路由训练 / 评测脚本
├─ data/                           # 路由数据集
├─ state/                          # 本地状态、trace、evaluation 日志
├─ tools/                          # migrate_prompt_skills.py
├─ server/                         # 服务包占位
└─ tests/
```

`ava/` 下的分工：

```text
ava/
├─ router_selector/            # 路由与 TurnPlan
├─ routing/                    # 旧导入兼容层
├─ inference_runtime/          # 消费 TurnPlan，选回复路径
├─ llm_model_executor/         # OpenAI Responses / Agents SDK 执行后端
├─ intent/                     # Manager 与技能子 Agent 编排
├─ multi_turn_context_builder/ # 上下文编译
├─ domain/                     # 会话状态、记忆、多模态
├─ capabilities/               # LLM / ASR / TTS / Prompt 适配
├─ pipeline/                   # 实时会话、语音后处理、评估日志
├─ core/                       # trace、实时事件、错误策略
└─ interfaces/                 # HTTP 与 WebSocket
```

各包内部的文件说明和接口契约见对应 README / ARCHITECTURE，列在末尾。`scripts/` 里是早期的路由训练与评测脚本（`sft_train_router.py` LoRA 蒸馏、`build_router_dataset.py`、`bench_router.py`、`eval_intent.py`、`quantize_router.py`、`serve_router_llama.ps1`）；`data/` 里是 `router_sft_train.jsonl` / `router_sft_train_mm.jsonl`（文本与多模态 SFT）、`router_sft_posneg.jsonl` / `router_sft_posneg_mm.jsonl`（正负样本对）、`router_golden.jsonl` / `router_golden_mm.jsonl`（评测金标）和 `mm_images/`；`state/` 存 `memory.json`、`evaluation.jsonl`、trace 日志、`agents_sessions.json`。`tests/` 覆盖配置加载与 include 合并、上下文编译、端云路由、技能编排器、状态白名单 patch、视觉延续、Agent 技能后端、实时事件、回复服务和追踪。

## 端侧小模型

高频路由下沉到本地小模型，复杂生成留给云侧 DeepSeek。`edge_router/` 是剪枝、量化、部署、评测和微调的实施目录，完整操作命令见 `edge_router/README.md`。

| 脚本 | 用途 |
|---|---|
| `download_vlm.py` / `download_models.py` | 下载视觉基座 Qwen2-VL-2B-Instruct 与文本小模型 Qwen2.5-0.5B-Instruct |
| `prune_router.py` | 语言解码层深度剪枝（保留首尾层与视觉塔），输出 `prune_report.json` |
| `quantize_router.py` | 语言层 Linear 动态 INT8 量化（视觉塔 fp32），输出 `quantize_report.json` |
| `serve_local.py` | OpenAI 兼容本地推理服务（:8080，真流式 + KV cache；`--no-quantize` 起 fp32 基线） |
| `build_mm_dataset.py` | 合成多模态路由数据集（图片 artifact + 路由标签） |
| `build_posneg_dataset.py` | 构建正负样本对（正确路由 vs 扰动错误路由） |
| `sft_posneg.py` | 正负样本微调（contrastive margin / DPO） |
| `recover_sft.py` | assistant-only SFT 流水线（smoke 可跑通验证） |
| `eval_router.py` | 性能（体积/压缩/首 token p50/p99/延迟/吞吐）与效果（路由准确率，文本/多模态，量化 vs 基线的精度损失） |

正负样本微调在同一 prompt 下构造正样本（正确路由 JSON）和负样本（场景、意图或模块错配的「自信但错误」JSON），损失为 `w_sft·(-mean_logπ(pos)) + w_margin·max(0, margin - (mean_logπ(pos) - mean_logπ(neg)))`，可选 DPO（带冻结参考模型），用来抬高正样本似然、压低负样本似然。默认 smoke 步数只验证链路可跑通，不做完整训练，也不覆盖部署模型。

降级由 `intent_config` 控制：`provider=local` 时路由先走端侧（`timeout_ms` 内），超时、异常或置信度低于 `min_confidence` 时降级云侧，`cloud_fallback_enabled` 控制开关，降级原因落 trace。

2B 视觉模型在纯 CPU 上首 token 和总延迟都偏高，只适合一次性的图片→文本视觉分析（结果缓存复用）；高频文本路由交给 0.5B 小模型，复杂或低置信度的路由由云侧 DeepSeek 兜底。

## 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/` | 返回前端演示页 |
| GET | `/health` | 健康检查 `{"status":"ok"}` |
| POST | `/api/router/test` | 生产链路路由测试：`{text,image_url,mode:full\|classify\|plan,prior_scene}`，返回分类/规划/summary/raw/延迟/provider |
| POST | `/api/router/edge` | 端侧小模型直测：`{text,image_url,max_tokens}`，返回首 token/总延迟/原始输出/解析 JSON |
| GET | `/api/router/contract` | 路由契约与端云配置概览 |

WebSocket 是 `/ws/audio?session_id=<id>`。连接后服务端先发 `hello`（协议版本、音频格式、player_url、session_id、最近历史、暂存附件）。客户端发送原始 PCM 二进制帧（按固定帧聚合送 ASR），或 JSON `type`：`text`（可带 attachments）、`interrupt`、`mic_stopped`、`ping`、`playback_started`、`stage_attachments`、`clear_staged_attachments`。服务端回推 ASR partial/final、路由决策、Prompt/strategy 调试、assistant token、TTS chunk、turn 完成、错误 / 控制事件。

## 配置

主配置 `configs/config.yaml` 通过 `config_files` 递归 include `asr_config/`、`llm_config/`、`tts_config/`；`configs/settings.py` 负责 YAML 读取、include 合并、Pydantic 校验和环境变量覆盖，并支持 gitignored 的 `xxx.local.yaml` 覆盖层。关键配置组是 `server` / `runtime` / `speech_postprocess` / `openai_config` / `asr_config` / `voice_config` / `intent_config`（端云路由开关、provider、local 小模型、`min_confidence`、`cloud_fallback`、cache）。ASR 可切 qwen3_asr / dou_bao，TTS 可切 cosyvoice / step_fun / dou_bao。

密钥不要写进仓库，用环境变量或 `*.local.yaml` 注入，例如主流程 DeepSeek 写 `configs/llm_config/llm_config.local.yaml`，端侧路由开关写 `configs/config.local.yaml`。仓库里曾经提交过的密钥应当轮换。

关键环境变量：`STREAMING_AVA_OPENAI_API_KEY`、`STREAMING_AVA_TTS_PROVIDER` / `..._TTS_API_KEY`、`STREAMING_AVA_STEPFUN_API_KEY`、`STREAMING_AVA_DOUBAO_X_API_KEY`、`STREAMING_AVA_ASR_PROVIDER` / `..._ASR_API_KEY`、`STREAMING_AVA_QWEN_ASR_API_KEY`、`STREAMING_AVA_DOUBAO_ASR_X_API_KEY`、`STREAMING_AVA_EDGE_VISION_API_BASE`。

## 依赖与文档

Python `>=3.11`。`fastapi` / `uvicorn`（HTTP + WS）、`openai` / `openai-agents`（Responses + Agents SDK）、`pydantic` / `pyyaml`（配置校验）、`sympy` / `lark`（数学口语化）、`dashscope` / `fastrtc`（语音）、`torch` / `transformers`（端侧小模型剪枝 / 量化 / 推理 / 微调）、`httpx`（端侧调用）。

项目内其他文档：

- `edge_router/README.md`（端侧小模型完整操作命令与指标）
- `ava/router_selector/README.md` / `ARCHITECTURE.md`
- `ava/multi_turn_context_builder/README.md`
- `ava/inference_runtime/README.md` / `ava/llm_model_executor/README.md`
- `ava/domain/README.md` / `ava/domain/memory/ARCHITECTURE.md`
- `ava/capabilities/llm/README.md` / `prompt-plugin/README.md`
- `ava/routing/README.md`（兼容层说明）
- `IMPLEMENTATION_BLUEPRINT.md` / `MULTI_INTENT_SUBAGENT_DESIGN.md`
