# 多意图识别 + 子 Agent 协作架构设计方案

> 状态：**仅方案，未改任何业务代码**。关键取舍已评审确认，可据此进入实现。
> 面向项目：`streaming-ava`（实时语音多模态对话后端）
> 日期：2026-11-16

---

## 0'. 已确认决策（评审结论，作为本方案约束）

| # | 议题 | 已定结论 |
|---|---|---|
| 1 | 子 Agent 执行方式 | **初版串行**（按优先级顺序执行，契合 TTS 单流与状态一致性）；并行留作二期 |
| 2 | 小模型接入方式 | **API 模式与本地进程内两种都支持，通过开关切换**，共用同一 provider 协议 |
| 3 | 多意图回复形态 | **合并成一条**统一 assistant 回复/单 token 流 |
| 4 | 本地模型权重与量化 | 已联网调研，选型见 **第 5.3 节**：Qwen3-4B + Q5_K_M（GGUF），官方源 Apache-2.0 |
| 5 | 硬编码 API Key 治理 | **本轮一并治理**（详见第 11 节） |

---

## 0. 一句话概述

把当前"单意图 → 单一执行链"的路由模型，升级为"**小参数 LLM 多意图识别 → 意图仲裁 → 多个子 Agent 串行协作 → 合并为一条回复**"的模型；意图识别独立成可用 API 或本地权重两种启动方式、可开关切换的模块；全程复用现有四层架构与事件系统，尽量以新增模块 + 配置开关的方式落地，降低对实时链路的冲击。

---

## 1. 现状基线（基于真实代码，非 README）

设计必须锚定代码事实，先列关键基线：

| 事实 | 代码位置 | 对新方案的含义 |
|---|---|---|
| 执行主干为四层：`multi_turn_context_builder → router_selector → inference_runtime → llm_model_executor` | `ava/router_selector/ARCHITECTURE.md:5-10` | 新模块须嵌入这四层，不另起炉灶 |
| `RouteDecision` 是**单意图**：`intent: str`、`turn_scene: str`、`confidence: float` | `ava/router_selector/schema.py:8-16` | 需扩展为多意图结构（保持向后兼容） |
| `router_plan` 是**无 schema 校验的裸 dict**，完全信任模型输出 | `ava/router_selector/service.py:236` | 意图结构必须由 Pydantic 强校验，不能沿用裸 dict |
| `TurnPlan` 是 router 交给 runtime 的**唯一正式对象**，字段 frozen | `ava/inference_runtime/types.py:99-133` | 多意图结果需挂到 TurnPlan 的新字段 |
| `BranchStrategy` 为 frozen dataclass，含 `analysis/router_plan/prompt_package` 等 | `ava/domain/conversation/strategy.py:148` | 每轮只有一个 strategy，多意图需要"子策略列表" |
| Agents SDK 已有 3 个 specialist agent 通过 `.as_tool()` 成为 manager 工具，`parallel_tool_calls=False` | `ava/llm_model_executor/agent_backend.py:526-549,185-190` | 已有"多角色协作"雏形，可复用而非重造 |
| 已有 4 个 `function_tool`：get_turn_plan / get_recent_history / get_reference_materials / note_state_patch | `ava/llm_model_executor/agent_backend.py:332-399` | 子 Agent 的工具契约可沿用 |
| 事件系统 `BaseRealtimeEvent.to_payload()` 把 event_type 改名 `type` | `ava/core/events/realtime.py:17-20` | 新增子 Agent 事件走同一事件总线 |
| `.as_tool()` 调用受 `agents_sdk_enabled` / `agents_sdk_realtime_enabled` / 分支模块白名单控制 | `ava/inference_runtime/service.py:45-66` | 新方案应新增独立开关，默认关闭 |
| `RouterService.route()` 把 `api_base/api_key` 塞进 metadata 但执行层只消费 `extra_body`，自定义端点实际不生效 | `router_selector/service.py:216-227`、`llm_model_executor/service.py:243-267` | 小模型的 API/本地端点必须设计成真实可配置并验证生效 |
| 配置统一前缀 `STREAMING_AVA_`，手写字段覆盖 | `configs/settings.py:147-180` | 新增意图配置需同步扩展覆盖逻辑 |

**结论**：项目已经有"多角色 Agent 协作"的骨架，但**意图识别仍是大模型顺带输出、单值**。本次改造的核心是"把意图识别拆出来并做成多值 + 独立小模型"，以及"把已有 Agent 能力显式化为可编排的子 Agent 池"。

---

## 2. 总体架构与职责边界

### 2.1 目标架构（新增/改造部分以 ★ 标注）

```
用户消息(文本/ASR final + 附件)
        │
        ▼
[1] multi_turn_context_builder   (现状) 规范化消息、拼历史
        │  ConversationContext
        ▼
[2] ★ IntentRecognizer（小参数 LLM，API/本地双模）  ← 新增
        │  IntentsResult(多条意图 + 置信度 + 槽位)
        ▼
[3] ★ IntentArbiter（纯规则，无 LLM）  ← 新增
        │  冲突消解 + 优先级排序 → ExecutionPlan(意图执行序列)
        ▼
[4] router_selector (改造)  RouteDecision + router_plan + PromptPackage
        │  主场景路由仍由 Router 负责；intents 由 [2][3] 注入
        ▼
[5] TurnPlan (扩展)  + sub_tasks: list[SubTask]
        │
        ▼
[6] ★ SubAgentOrchestrator  ← 新增（可复用现有 agent_backend）
        │  分发 → 子Agent执行 → 汇总
        │  每个子Agent: 复用 BranchStrategy + PromptPackage + tools
        ▼
[7] inference_runtime / llm_model_executor (改造) 统一生成 assistant token 流
        │
        ▼
[8] 事件总线 → assistant_token / tts_chunk / 汇总事件 → 前端
```

### 2.2 职责边界（谁做什么、谁不做什么）

| 模块 | 负责 | 不负责（明确边界） |
|---|---|---|
| **IntentRecognizer**（小模型） | 从当前消息抽取**候选意图列表**、槽位、置信度、是否需要澄清 | 不做场景路由、不选 Prompt、不生成回答、不做冲突消解 |
| **IntentArbiter**（规则） | 意图冲突判定、优先级排序、生成确定性执行序列 | 不调用 LLM、不改槽位内容、不生成文本 |
| **router_selector**（现状改造） | 主 `session_scene/turn_scene`、plan 归一化、Skill/PromptPackage 选择 | 不再单独判定 `intent`（改由识别器提供） |
| **SubAgentOrchestrator** | 子 Agent 生命周期、任务分发、取消、超时、结果汇总 | 不直接调模型 API（委托 llm_model_executor）、不改领域状态 |
| **子 Agent** | 在分配到的意图范围内，用其 PromptPackage + tools 产出**片段结果** | 不访问其他子 Agent 的私有上下文、不自行决定全局回复结构 |
| **inference_runtime** | 消费 TurnPlan、决定后端、驱动统一输出 | 不感知具体有几个意图（对上只看到"一轮执行"） |
| **llm_model_executor** | 真正发请求（Responses / Agents SDK） | 不理解意图语义 |

> 关键取舍：让 `inference_runtime` 对上仍只看到"一轮"，可最大限度保留现有 turn 生命周期、barge-in、TTS 单流播放等实时语义，避免大改 session.py（1409 行）。

---

## 3. 分支策略与实现步骤拆解

### 3.1 分支

```
main
  └─ feature/multi-intent-subagents        # 主开发分支
       ├─ feat/intent-recognizer-provider  # 小模型双模（可并行）
       ├─ feat/intent-arbiter              # 冲突与优先级（可并行）
       └─ feat/subagent-orchestrator       # 子Agent编排（可并行）
```

- 主干保护：`feature/multi-intent-subagents` 从 `main` 切出，各子分支 PR 合入它，最终一次性 PR 回 `main`。
- 全程用**配置开关** `runtime.intent_engine_enabled`（默认 `false`）控制：关闭时行为与现状完全一致，保证可随时回滚。
- 每个 PR 必须包含单元测试；端到端回归在开关关闭态跑一遍。

### 3.2 实现步骤（按依赖顺序，标注可并行）

| 阶段 | 步骤 | 交付物 | 依赖 |
|---|---|---|---|
| P0 | 定义新数据结构（IntentItem/IntentsResult/ExecutionPlan/SubTask/SubAgentResult） | `ava/intent/types.py` | 无 |
| P1 | 配置模型 + include + 环境变量覆盖 | `configs/intent_config/*`、`settings.py` 扩展 | P0 |
| P2a | 小模型 Provider 抽象 + API 模式 | `providers/base.py`、`providers/api.py` | P1 |
| P2b | 小模型本地模式（transformers/llama.cpp） | `providers/local.py` | P1 |
| P2c | 意图识别 Prompt 模板 + JSON 约束输出 | `ava/intent/prompts/*`、`prompt-plugin` 新增 intent skill | P0 |
| P3 | IntentRecognizer 编排 provider+prompt+校验 | `ava/intent/recognizer.py` | P2a/P2b/P2c |
| P4 | IntentArbiter 冲突与优先级（纯规则 + 单测） | `ava/intent/arbiter.py` | P0 |
| P5 | router_selector 扩展：注入 intents、保留兼容字段 | 改 `schema.py`/`service.py` | P3/P4 |
| P6 | TurnPlan 扩展 sub_tasks（frozen 兼容） | 改 `inference_runtime/types.py` | P5 |
| P7 | SubAgentOrchestrator + 子 Agent 池（复用 agent_backend） | `ava/intent/orchestrator.py` | P6 |
| P8 | 事件扩展 + 调试面板展示 | `ava/core/events/realtime.py`、`static/app.js` | P7 |
| P9 | 端到端联调、评测集、灰度开关 | 测试 + 文档 | 全部 |

P2a/P2b/P2c 与 P4 可并行开发；P5 之后为串行关键路径。

---

## 4. 多意图识别策略、冲突处理与优先级规则

### 4.1 识别策略（小参数 LLM）

- **模型定位**：仅做"抽取 + 分类 + 槽位"，是**判别式轻任务**，不生成最终回答。推荐 1.5B~7B 量级（如 Qwen2.5-3B/7B-Instruct、Qwen3-4B 等），中文与 JSON 遵循能力优先。
- **输出约束**：要求输出严格 JSON（非 markdown 包裹），用 Pydantic 校验；参考现有 router 的 `_extract_json_object` 容错做法，但**升级为失败重试 + 兜底降级**（LLM 输出不可靠时退回单意图）。
- **输入**：当前 user_message 文本 + 简要历史（最近 N 轮，避免小模型上下文过载）+ 可用意图清单（枚举约束）+ 当前 session_scene。
- **few-shot**：每个意图类型 1~2 例，控制 prompt 长度。
- **置信度校准**：要求模型对每个意图给 0~1 分数；可加"是否多意图"二分类先判，减少单意图误拆。
- **意图枚举**（初版建议，需讨论）：`solve / explain / fact / howto / clarify / confirm / smalltalk / reaction / drill / summarize / translate / translate_or_explain / set_state / other`。与 `prompt-plugin/components/task/` 现有 20+ 技能对齐。

### 4.2 冲突类型与处理规则

| 冲突类型 | 例子 | 处理策略 |
|---|---|---|
| 互斥意图 | "讲笑话" + "严肃解题" 语气冲突 | 保留优先级高者，其余降级为"次要意图"可选执行 |
| 包含/依赖 | "这道题我不会，讲一下" → clarify + solve | 合并：clarify 作为 solve 的前置步骤，不单独占一个子 Agent |
| 重复意图 | 同一 solve 被识别两次 | 按意图类型 + 槽位指纹去重，保留置信度高者 |
| 资源冲突 | 多个意图都要 TTS/同一状态键 | 串行化，或由仲裁器只允许一个写状态 |
| 超上限 | 一句话识别出 6 个意图 | 截断到 `max_intents_per_turn`（默认 3），其余丢弃并记 trace |

### 4.3 优先级规则（可配置，示例）

```
P0  interrupt / cancel / set_state(安全)      —— 立即执行，独占
P1  solve / drill / explain(教育主任务)        —— 高，教育场景延续优先
P2  fact / howto / summarize / translate       —— 中
P3  clarify / confirm                          —— 依附其主意图，不独立排序
P4  smalltalk / reaction / humor               —— 低，可被高优先级挤压
```

排序键（同优先级时依次比较）：`session_scene 延续性 > 置信度 > 文本出现顺序`。
所有规则集中在 `IntentArbiter` 的**规则表**（配置化），不写死在 prompt 里，便于评测调优。

---

## 5. 小参数 LLM 的 API / 本地双模接入

### 5.1 Provider 抽象（对齐现有 factory 风格）

```python
# ava/intent/providers/base.py
class IntentProvider(Protocol):
    def recognize(self, req: IntentRecognitionRequest) -> IntentRecognitionRaw: ...
    async def recognize_async(self, req: IntentRecognitionRequest) -> IntentRecognitionRaw: ...
    def health(self) -> bool: ...
```

> **关键简化**：经调研，`llama-server`（llama.cpp 自带）与 Ollama 都提供 **OpenAI 兼容 `/v1` 端点**。因此 API 模式与本地"外部服务"模式可**共用同一个 `api` provider**——切换仅改 `api_base`，无需两套代码。真正的第二种模式是**进程内本地推理**（无外部服务），用 `local` provider 直接加载权重。最终两类 provider：

| Provider | `provider` 值 | 启动方式 | 适用场景 |
|---|---|---|---|
| **OpenAI 兼容 API** | `api` | `api_base` 指向云 API / vLLM / Ollama(`/v1`) / `llama-server`(`/v1`) | 默认；部署灵活，切换零代码 |
| **进程内本地推理** | `local` | `backend: llamacpp \| transformers` + 本地权重路径 | 无外部服务、追求最低延迟/隐私 |

- 由 `build_intent_provider(config)` 工厂按 `provider` 开关创建；`IntentRecognizer` 只依赖协议。
- **必须规避**现有 `api_base/api_key` 被塞进 metadata 却被执行层忽略的坑：provider 自己持有 endpoint 并直接使用，且实现后必须用本地 mock server 验证端点真实生效。

### 5.2 配置草案（`configs/intent_config/intent_config.yaml`）

```yaml
intent_config:
  enabled: false
  provider: api                 # ★ 总开关：api | local
  max_intents_per_turn: 3
  timeout_seconds: 3.0
  temperature: 0.0              # 确定性输出
  use_json_schema: true         # 强制结构化输出
  # --- API 模式（含 OpenAI 兼容的本地服务）---
  api:
    api_base: "http://127.0.0.1:8080/v1"   # llama-server / Ollama / 云 API
    model: "qwen3-4b"
    api_key: ""                            # 云 API 时从环境变量注入
  # --- 进程内本地模式 ---
  local:
    backend: llamacpp            # llamacpp | transformers
    model_path: ""               # 本地 GGUF / HF 目录，见 5.3
    n_ctx: 4096
    n_gpu_layers: -1             # -1 = 全部卸载到 GPU；CPU-only 设 0
    device: "auto"
```
- 切换只需改 `intent_config.provider` 一个值（`api` ↔ `local`）。
- 主配置 `config.yaml` 的 `config_files` 增加该 include；`settings.py` 增加 `IntentConfig` 字段与 `STREAMING_AVA_INTENT_*` 覆盖（含 `..._API_BASE`、`..._MODEL`、`..._API_KEY`、`..._PROVIDER`、`..._MODEL_PATH`）。

### 5.3 本地模型选型（联网调研结论，2026-11）

**结论：主推 Qwen3-4B，量化档 Q5_K_M（GGUF）；显存充裕可升 Q8_0；极低配回退 Qwen3-1.7B。**

| 维度 | 选型 | 依据 |
|---|---|---|
| 模型族 | **Qwen3-4B-Instruct** | 多源（2026）一致评为中文最强小模型档、agent/工具调用强、原生支持 thinking/non-thinking 切换、100+ 语言、Apache-2.0 可商用；专为"脚本高频分类/抽字段/返 JSON"场景，Qwen3-4B 被列为首选平衡点 |
| 为何不更小 | 0.6B/1.7B 仅在内存极紧时用 | 小模型对 prompt 措辞敏感、结构化输出更易错；单一窄任务可以很好，但多意图分类+槽位+冲突信号偏复杂，4B 更稳 |
| 为何不更大 | 8B/14B 作兜底而非默认 | 类别细微/文本脏/4B 频繁出错时再升 8B，速度约减半 |
| 量化档 | **Q5_K_M**（约 2.7GB，Qwen3-4B） | 结构化输出"一个错误 token 就破坏结果"，多源明确建议此类任务用 **Q5_K_M 或 Q6_K** 而非通用 Q4_K_M；llama.cpp 参考：8B 上 Q5_K_M 比 Q4_K_M 困惑度误差降约 3 倍，体积仅 +16% |
| 量化档备选 | Q8_0（~4GB，近无损）/ Q4_K_M（~2.3GB，内存紧张） | 显存/内存充裕用 Q8_0；8GB 机器用 Q4_K_M 或 Q3_K_M |
| 格式 | **GGUF**（llama.cpp / Ollama / llama-server 通用） | 单文件含权重+tokenizer+元数据；Mac 可选 MLX，其余平台用 GGUF |

**权重来源（谁提供）**：直接采用官方仓库，不自训练——
- 官方 GGUF：`Qwen/Qwen3-4B-GGUF`（Hugging Face / ModelScope），提供 q4_K_M / q5_K_M / q6_K / q8_0 官方量化，Apache-2.0。
- 下载由**部署/运维**在执行脚本时拉取到 `state/models/` 或配置的 `model_path`（不入库，避免大文件进 git）；代码只认路径配置。
- 精确下载命令示例（实现时写入 `scripts/`）：
  - llama.cpp：`./llama-server -hf Qwen/Qwen3-4B-GGUF:Q5_K_M --jinja -ngl 99 --port 8080`
  - Ollama：`ollama run hf.co/Qwen/Qwen3-4B-GGUF:Q5_K_M`

**结构化输出可靠性措施**（调研一致建议）：
1. 用 JSON Schema 约束（`format`/`response_format` + json_schema），把意图类型做 `enum`，只允许枚举内取值；
2. `temperature=0`，system prompt 放规则、user 只放待分类文本；
3. 加 2~3 个 few-shot；
4. 保留 `other / unsure` 出口，避免强行归类产生自信错误；
5. Qwen3 追加 `/no_think` 关闭思维链（分类任务无需推理，省延迟）；
6. 上线前人工标注 50~100 条样本评测，选"够用且最快"的最小档。

> 补充参考：业界已有"小模型蒸馏做意图分类"成功先例（Qwen3-0.6B 蒸馏后工具调用准确率 96.7%，超过 120B 教师），说明本方向可行；本项目初版不做蒸馏，仅用通用 instruct 模型 + 强约束。

---

## 6. 子 Agent 通信机制

### 6.1 统一消息信封（Envelope）

所有子 Agent 与编排器之间的消息走统一 JSON 信封，便于落 trace、回放与调试：

```json
{
  "msg_id": "uuid",
  "turn_id": "t-20261116-001",
  "trace_id": "tr-xxx",
  "type": "task.assign | task.result | task.error | state.patch | control.cancel | heartbeat",
  "src": "orchestrator | subagent:solve",
  "dst": "subagent:solve | orchestrator | aggregator",
  "correlation_id": "task-1",
  "intent_id": "i-1",
  "seq": 1,
  "ts_ms": 1730000000000,
  "payload": { "...": "类型相关" },
  "meta": { "attempt": 1, "timeout_ms": 8000 }
}
```

- `correlation_id` 贯穿一次子任务全链路；`seq` 保证同一意图的流式片段有序。
- 消息即事件：`task.assign/result/error` 同步发一份到现有事件总线（新增 `subagent_*` 事件），前端调试面板可见。

### 6.2 任务分发

- Orchestrator 把 `ExecutionPlan` 的每个可执行意图包成 `SubTask`，调用 `dispatch(subtask)`。
- 分发策略：**已确认初版串行**——按 `ExecutionPlan` 的优先级顺序逐个执行，天然契合 TTS 单流、状态一致性最好，也简化取消/汇总逻辑。并行（互相独立的意图如 fact + translate 并发）留作二期，届时需为每个子 Agent 提供独立上下文快照并按序汇总。
- 每个子 Agent 复用其意图对应的 `BranchStrategy + PromptPackage`，并通过 `subagent_id` 隔离会话状态。

### 6.3 状态同步

- **只读快照**：子 Agent 启动时拿到 `ConversationContext` 不可变快照，避免并发写冲突。
- **状态补丁**：子 Agent 不直接改 `ConversationState`；通过 `state.patch` 消息提交补丁，由 Orchestrator 在主线程**串行 apply**（复用现有 `RuntimeAgentContext.add_patch` 思想）。
- **共享键白名单**：仅允许修改配置白名单内的 key；冲突键由仲裁器裁决。
- 落盘仍走现有 `state_file`，不新增第二套持久化。

### 6.4 结果汇总

- 每个子 Agent 产出 `SubAgentResult(status, text_segments, patches, confidence, error)`，text 以流式片段返回。
- Aggregator 按 `ExecutionPlan` 顺序拼接：
  - 加轻量过渡语（可配置开关，默认关闭以避免啰嗦）；
  - 统一成一个 `assistant_message` 与一条 token 流 → 供 TTS 单流播放；
  - 汇总后调用 `ConversationState.complete_realtime_turn()`（沿用现有生命周期）。
- 部分成功：失败的意图跳过并在 trace 标记，回复中不出现其内容；全部失败则触发整体降级。

### 6.5 异常处理

| 场景 | 处理 |
|---|---|
| 子 Agent 超时 | 按 `timeout_ms` 取消，retry 1 次，仍失败则该意图降级 |
| 子 Agent 抛错 / 输出非法 | 捕获 → `task.error`，该意图走"主 LLM 直接回答"兜底 |
| 意图识别失败 | 整体降级为**现状单意图路径**（开关级兜底，保证可用性） |
| 用户打断（barge-in） | Orchestrator 广播 `control.cancel` 给所有在途子 Agent，丢弃在途 token/tts（复用 `session.interrupt` 既有机制） |
| 资源竞争 | 串行 apply patches；写冲突按优先级仲裁 |

---

## 7. 与现有流程的集成点

| 集成点 | 现状 | 改动 |
|---|---|---|
| `router_selector/service.py:route()` | 大模型输出单 intent | 在 route 前调用识别器；route 结果合并 `intents`；保留 `intent` 为主意图（兼容） |
| `schema.py:RouteDecision` | 单值字段 | 新增 `intents: list[IntentItem]`、`intent_plan`（可选），旧字段保留 |
| `inference_runtime/types.py:TurnPlan` | frozen，无子任务 | 新增 `sub_tasks` 字段（默认空），兼容构造点 |
| `inference_runtime/service.py` | `_should_use_agents_backend` 决定后端 | 新增"是否走多意图编排"分支；开关关闭时原路径不变 |
| `llm_model_executor/agent_backend.py` | 已有 manager + 3 specialist | 把 specialist 显式纳入子 Agent 池；必要时新增通用 sub-agent 生成器 |
| `core/events/realtime.py` | 19 类事件 | 新增 `intent_recognized / subagent_started / subagent_result / aggregation_done` |
| `static/app.js` `handleEvent()` | 覆盖现有 type | 增加新事件的调试展示（意图列表、子 Agent 状态、耗时） |
| `configs/settings.py` | 手写环境变量覆盖 | 增加 `STREAMING_AVA_INTENT_*` 系列 |

**不变的关键约束**：`session.py` 的 turn 生命周期、`interrupt()`、`_run_turn()` 单 token 流、TTS 单流播放——尽量不改。

---

## 8. 关键数据结构调整（草案）

```python
# ava/intent/types.py
class IntentItem(BaseModel):
    intent_id: str
    intent_type: str            # 见 4.1 枚举
    confidence: float = 0.0
    slots: dict[str, Any] = {}
    evidence: str = ""          # 触发该意图的原文片段
    priority: int = 4           # 由识别器粗标，仲裁器可覆盖
    needs_clarification: bool = False

class IntentsResult(BaseModel):
    intents: list[IntentItem]
    session_scene_hint: str = ""
    raw_output: str = ""
    provider: str = ""
    latency_ms: int = 0

class ExecutionIntent(BaseModel):   # 仲裁后
    item: IntentItem
    order: int
    mode: Literal["primary", "secondary", "dependent", "dropped"]
    reason: str = ""

class ExecutionPlan(BaseModel):
    intents: list[ExecutionIntent]
    conflicts: list[dict[str, Any]] = []

class SubTask(BaseModel):
    task_id: str
    intent: ExecutionIntent
    prompt_package_ref: str     # 指向已编译的 PromptPackage
    tools: list[str] = []
    timeout_ms: int = 8000

class SubAgentResult(BaseModel):
    task_id: str
    status: Literal["ok", "partial", "failed"]
    text_segments: list[str] = []
    patches: list[dict[str, Any]] = []
    error: str | None = None
```

兼容策略：`RouteDecision.intent` 填 `ExecutionPlan` 中 order=0 的意图类型；新增字段均带默认值，旧代码读取不受影响。

---

## 9. 测试验证方式

1. **单元**
   - Provider：API 模式用本地 mock HTTP server；本地模式用假模型（或极小测试权重）验证加载与输出解析。
   - 识别器：构造 LLM 输出样本（合法 JSON、带 ``` 包裹、残缺 JSON、空输出）验证容错与降级。
   - 仲裁器：规则表驱动的表格测试（每条冲突类型 ≥1 用例）。
   - 信封序列化/反序列化、seq 有序性。
2. **集成**
   - 端到端：mock 识别器返回多意图 → 验证分发、汇总、单一 token 流、落盘 turn 记录。
   - barge-in：子 Agent 执行中触发 `interrupt`，验证 cancel 广播与在途 token 丢弃。
   - 降级：识别失败、provider 不可用、开关关闭三条路径均回到现状行为。
3. **评测集**
   - 人工标注 100~200 条多意图语句（含 ASR 口语、错别字、附件场景），对比单意图基线的意图召回/精确、冲突处理正确率。
   - 延迟：P50/P95（识别延迟、总首 token 延迟），设阈值防劣化。
4. **回归**：开关关闭态跑现有测试集，行为必须与当前完全一致。

---

## 10. 不完善点、风险与待确认问题

### 10.1 方案不完善点
- 子 Agent 的**会话记忆隔离**只给了快照方案，跨轮记忆如何在子 Agent 间共享/继承尚未细化（现有 `SessionMemory` 检索/投影本就是未接线孤岛）。
- 初版为串行，"结果有序 + TTS 单流"较自然；但多意图之间的过渡语、断句、韵律仍未设计，串行下仍需避免拼接生硬。
- 本地进程内模式的**模型生命周期**（预热、常驻、显存回收、多 session 并发）未定；API 模式（llama-server/Ollama）由外部服务托管，无此问题。
- 意图枚举与现有 20+ task skill 的映射需逐一对齐，本稿只给了初版。
- 前端 UI 只列了要加的事件展示，未设计多意图的可视化交互。

### 10.2 风险
- **准确率风险**：小模型对中文口语、ASR 错字、隐含意图的识别可能明显弱于现用大模型，误拆/漏拆会直接劣化体验。
- **延迟风险**：多一次识别推理 + 多 Agent 执行，首 token 延迟叠加，实时对话体验敏感。
- **一致性风险**：多个子 Agent 写状态、多意图合并成单一回复，可能出现语气割裂或状态冲突。
- **资源风险**：本地进程内权重常驻显存（API 模式可缓解）；串行执行吞吐较低但资源占用可控。
- **兼容风险**：现有 `api_base/api_key` 失效问题若不在新模块彻底解决，小模型接入会重蹈覆辙。
- **进度风险**：`session.py`（1409 行）与 agent_backend 耦合较深，集成点一旦需要深入改动，工期不确定性大。

### 10.3 评审结论（已拍板，转为约束）
1. ~~子 Agent 串行/并行？~~ → **串行**（见 0' 节）。
2. ~~小模型 API 还是本地？~~ → **两种都支持，开关切换**（见 0' 节、第 5 节）。
3. ~~多意图合并/分条？~~ → **合并成一条**（见 0' 节）。
4. ~~模型文件与量化谁提供？~~ → **官方 Qwen3-4B-GGUF / Q5_K_M，部署时下载到配置路径**（见 5.3）。
5. ~~是否治理硬编码 API Key？~~ → **本轮一并治理**（见第 11 节）。

### 10.4 仍需后续确认的开放问题（不阻塞开工）
1. 意图枚举最终清单与 `max_intents_per_turn`（暂定 3）——需与 `components/task/` 20+ skill 逐一对齐。
2. 是否需要跨轮"意图历史 / pending 意图"持久化？
3. 复用现有 3 个 specialist agent，还是为新意图动态生成通用子 Agent？（初版建议：沿用现有 + 通用兜底）
4. 灰度按 session 还是全局，是否需要 per-user 白名单？（初版建议全局开关）
5. 识别失败/低置信：降级单意图还是走澄清？（初版建议：失败降级单意图，低置信且 `need_clarification` 走澄清）
6. 已暴露的旧 API Key 需由密钥所有者**在第三方平台轮换**——代码层只能移除，无法代做轮换。

---

## 11. 硬编码 API Key 治理（本轮确认执行）

### 11.1 现状（已核实）
以下文件直接提交了疑似真实密钥字段（值形如真实 key），且 README 却建议用环境变量，二者矛盾：
- `configs/llm_config/llm_config.yaml`（`openai_config`/`bigmodel_config` 的 `api_key`）
- `configs/asr_config/asr_config.yaml`（dashscope / doubao 的 `api_key`/`x_api_key`）
- `configs/tts_config/tts_config.yaml`（cosyvoice / step_fun / doubao 的 `api_key`）

### 11.2 治理原则
- **不破坏加载**：`settings.py` 的 Pydantic 模型字段保持存在，默认值改为空串；缺值时服务应明确报错而非用假 key 静默请求。
- **环境变量优先**：现有 `STREAMING_AVA_*` 覆盖链继续作为主要注入方式；补齐遗漏 provider 的覆盖变量。
- **示例文件可提交，真实值不提交**：提供 `*.example.yaml`（带占位符）供参考；真实值只从环境变量或本地未跟踪文件注入。
- **本地开发便利**：`.gitignore` 已含 `/configs/model_config.example.yaml`、`/configs/system_config.example.yaml`；建议新增忽略本地覆盖文件（如 `configs/**/*.local.yaml`），开发者把真实值放这里。

### 11.3 执行步骤（实现阶段，独立 PR）
1. 将上述 3 个 yaml 的密钥字段值替换为 `""` 或 `"${ENV_VAR}"` 占位说明（保留字段结构）。
2. check `settings.py`：确认每个 provider 的 `api_key` 都有对应环境变量覆盖；补充缺失项（如 `bigmodel_config`、`step_fun`、qwen asr 已有则跳过）。
3. 新增 `configs/**/*.local.yaml` 到 `.gitignore`；补充一份脱敏的示例说明。
4. 启动校验：不设环境变量时，相关 provider 初始化报"缺少 API Key"的清晰错误；设置后正常。
5. **安全提示（必须转达用户）**：由于旧 key 已进入 git 历史，仅删除当前文件不够；**需在各第三方平台轮换这些 key**，并考虑用 `git filter-repo`/BFG 清理历史（高风险操作，需另行评估，本方案不擅自执行）。

---

## 附：本方案与 README 的关系

修复后的 README 已恢复可读，但其描述的目录（如 `context_engine/`、`pipeline/generation/`）多与真实代码不符。本方案一律以**真实代码**为准；建议在进入实现前，同步启动一次 README 架构章节的校正（可作为独立 PR），避免方案与文档口径再次分叉。
