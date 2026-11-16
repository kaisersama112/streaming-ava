# streaming-ava 整体落地实施方案（六大模块）

> 性质：**实施方案 / 工程蓝图**，供评审与排期。本文在 `MULTI_INTENT_SUBAGENT_DESIGN.md` 基础上扩展到用户提出的全部 6 大模块。
> 代码状态：本文产出时未改动业务逻辑代码（API Key 治理除外，见文末附注）。
> 原则：一切以**真实代码**为准，逐项标注"已有 / 需增强 / 需新建"，并诚实区分"可由代码直接落地"与"需数据/训练/压测才能达成的指标"。
> 日期：2026-11-16

---

## 0. 阅读指引与三条硬约束

### 0.1 三类内容必须分清
| 类别 | 含义 | 本文如何处理 |
|---|---|---|
| **可代码落地** | 架构、协议、数据结构、编排、埋点、缓存等 | 给出目录、接口、步骤、验收 |
| **需数据/训练的工程** | SFT 微调、蒸馏、量化压缩、评测集 | 给出可执行的工程流程与工具链，但**不承诺指标数值** |
| **指标目标（KPI）** | 【压缩 70%】【精度损失 <5%】【首 token 700ms】【P99 5000→1500ms】 | 作为**验收目标**，给出达成路径与测量方法；数值须在真实硬件/数据上实测确认 |

### 0.2 与已确认决策的衔接
前序已拍板：子 Agent 初版串行、小模型 API/本地双模可切换、多意图合并为一条回复、模型选型 Qwen3-4B + GGUF Q5_K_M。本方案全部沿用；用户本次提到的"3B"与"INT8/GPTQ/AWQ"在第 2 节给出**取舍说明**（与端侧 GGUF 路线的关系）。

### 0.3 一个重要的现实提醒
当前项目**没有** `tests/`、没有评测集、没有训练数据、没有 CI 压测环境。本方案中"验证/评测/压测"相关能力本身也需要搭建（列为 P0 配套任务），否则 KPI 无法被证伪。

---

## 1. 现状差距总表（先看清家底）

| 模块 | 用户目标 | 真实代码现状 | 差距定性 |
|---|---|---|---|
| ① 多智能体架构 | Router/Responder/Manager + 解题/批改/讲解/学情评估子 Agent，串/并/条件编排，状态白名单 patch | 四层主干清晰；已有 manager + 3 specialist（history/message_block/prompt_package）；`RuntimeAgentContext.add_patch` 已存在 | **部分已有**：需把 specialist 扩展为技能 Agent 池、编排显式化、patch 白名单化 |
| ② 小模型端云协同 | Router 下沉 3B，SFT/蒸馏/量化，ONNX/llama.cpp/MNN，KV Cache 优化，云兜底 | 无任何本地推理代码；Router 走云 API；已调研 Qwen3-4B GGUF 方案 | **需全新建**（本文已给选型与流程） |
| ③ 链路优化 | 并行预取/技能并行/流式/缓存/裁剪，P99 1500ms，previous_response_id 连续对话，动态选模 | 流式已有；`previous_response_id` 字段已存在但执行层不用；无中间结果缓存、无动态选模 | **部分已有**：启用字段 + 新增缓存/裁剪/选模 |
| ④ 上下文工程 | Context Compiler 编译 system/developer/history/user，技能/状态注入，历史裁剪，多模态拼装 | `ContextCompiler` 已存在但只做消息规范化+历史拼装+instructions；无 system/developer 分层，无记忆注入 | **需增强**：这是"已有壳、缺内涵" |
| ⑤ 记忆与多模态 | SessionMemory+ConversationState 双层，turn_records 事实源，槽位/摘要/教育态/附件缓存，引用继承与上下文隔离 | 双层结构**完整存在**；但检索/投影/附件缓存 API 是**未接线孤岛**；`MediaArtifact` 主流程不用 | **需接线**：骨架齐全，缺生产调用 |
| ⑥ 实时交互与可观测 | ASR/LLM/TTS/WS 串联、barge-in、未完成 turn 保留、全链路 trace/eval | 全部**已实现且较完整**；trace 用 `append_trace_log`；eval 有 evaluation_logger | **基本已有**：补埋点维度与 barge-in 前端接线 |

**一句话**：⑥ 基本成品、⑤ 是"接线"、④ 是"填充"、① 是"扩展"、③ 是"启用+新增"、② 是"从零"。按此顺序排期，风险最低、见效最快。

---

## 2. 模块① 多智能体架构设计（Router + Responder/Manager + 技能子 Agent）

### 2.1 目标与边界
把"分类 / 规划 / 生成"从单次推理彻底拆开：

```
Router（小模型，高频低延迟）  →  意图识别 + 场景路由 + 计划生成（RouteDecision + router_plan）
        ↓ ExecutionPlan
Manager/Responder（云端大模型，Agents SDK）  →  最终回答 + 工具执行 + 技能调度
        ↓ 分发
技能子 Agent：解题 solve / 批改 check / 讲解 explain / 学情评估 assess
```

### 2.2 与现有代码对齐的落地设计

**已有可复用**：
- Manager 骨架：`_build_manager_agent()`（`agent_backend.py:485`），已挂 3 个 specialist 的 `.as_tool()`（:526-549）
- 工具契约：4 个 `function_tool`（:332-399），其中 `note_state_patch` 已是 patch 机制雏形
- 策略对象：`BranchStrategy`（`domain/conversation/strategy.py:148`）承载 branch/module/pedagogy/prompt_package

**需新建/改造**：

| 项 | 做法 | 落点 |
|---|---|---|
| Router 独立化 | 把意图识别从 RouterService 顺带输出中拆出，接入 `IntentRecognizer`（见方案文档第 4/5 节） | `ava/intent/`（新） |
| 技能子 Agent 池 | 把 3 个 specialist 扩展为 4 个技能 Agent：solve/check/explain/assess；每个绑定 `prompt-plugin/components/task/` 对应 Skill | `agent_backend.py` 改造 + `prompt-plugin/components/task/assess/`（新） |
| 编排器 | 初版串行（已定）；框架预留 `serial / parallel / conditional` 三种模式 | `ava/intent/orchestrator.py`（新） |
| 状态白名单 patch | 见 2.3 | `RuntimeAgentContext` + Orchestrator |

### 2.3 状态白名单 patch 机制（重点，防运行期污染）

**问题**：Agent 若可直接改 `ConversationState`，一次越权写入即污染核心会话事实源。

**设计**：
```python
# 1) 白名单：只有这些 key 可由 Agent patch（教育态 + 轻量连续性字段）
AGENT_PATCH_WHITELIST = {
    "subject", "knowledge_point", "stage", "level", "learning_scenario",
    "learning_objects", "object_scope", "primary_action", "answer_boundary",
    "recent_topic_hint",
}

# 2) Agent 只提交 patch，不直接改 state（note_state_patch 已具备此形状）
@function_tool
def note_state_patch(ctx, key: str, value: str, reason: str):
    if key not in AGENT_PATCH_WHITELIST:
        return f"REJECTED: {key} 不在白名单"
    ctx.context.add_patch(key=key, value=value, reason=reason)

# 3) Orchestrator 在主线程串行 apply（唯一写入点）
def apply_patches(state: ConversationState, patches: list[StatePatch]):
    for p in patches:
        if p.key in AGENT_PATCH_WHITELIST and _validate(p):
            state.set_education_state_value(p.key, p.value)  # 仅教育态入口
            append_trace_log({"event": "state.patch.applied", **p})
        else:
            append_trace_log({"event": "state.patch.rejected", **p})
```

**约束**：
- 白名单外的 key（如 `session_scene`、`turn_records`、`memory`、`intent_counter`）一律拒绝。
- patch 全量落 trace（key/value/reason/来源 agent），可审计可回放。
- 写冲突（多个 Agent patch 同 key）按执行顺序后者覆盖，或按优先级仲裁（串行下按序即可）。

### 2.4 协作协议（与消息信封统一）
沿用 `MULTI_INTENT_SUBAGENT_DESIGN.md` 第 6 节的 JSON 信封：`task.assign / task.result / task.error / state.patch / control.cancel`，含 `correlation_id / seq / turn_id`，并同步发一份到事件总线。

### 2.5 编排模式（初版串行，框架留全）
| 模式 | 初版 | 说明 |
|---|---|---|
| serial | ✅ 启用 | 按 ExecutionPlan 顺序，契合 TTS 单流、状态一致性 |
| parallel | 🔜 二期 | 独立技能（如 explain + assess）并发，需独立上下文快照 |
| conditional | 🔜 二期 | `need_clarification` / 低置信时跳到澄清分支 |

### 2.6 验收
- 单测：白名单内 patch 应用成功、白名单外被拒、落 trace；3 种编排模式各 1 条端到端用例。
- 集测：一次多意图轮次，验证 4 个技能 Agent 均被调用且状态无越权写入。

---

## 3. 模块② 小模型侧端部署与调优（端云协同）

### 3.1 目标形态
```
Router 链路（意图/场景/计划）── 3B 小模型，端侧/本地，高频低延迟
复杂生成（回答/推理）      ── 云端大模型（qwen-plus / glm 等）
失败或低置信              ── 云侧兜底降级
```

### 3.2 关于"3B"与量化格式的取舍说明（重要）
- 用户写"3B"，前序调研定"Qwen3-4B"。二者属同一量级；**Qwen3-4B 在中文与工具调用上更强**，建议保留；若强约束 3B，可用 `Qwen3-1.7B` 或 `Qwen2.5-3B`，但意图分类准确率需实测。
- 用户提"INT8/GPTQ/AWQ"是**服务端/通用量化**术语；前序调研定的 **GGUF Q5_K_M** 是 **llama.cpp/Ollama 端侧**路线。二者不冲突但面向不同运行时：
  - 端侧（llama.cpp/MNN/ONNX Runtime）→ GGUF / INT8
  - 云端 vLLM 服务 → GPTQ / AWQ
- 本方案建议：**端侧用 GGUF Q5_K_M（已调研）；若走 ONNX Runtime/MNN 则另导出 INT8 量化模型**。GPTQ/AWQ 仅在与 vLLM 云部署结合时采用。

### 3.3 SFT 微调与蒸馏（工程流程，非代码承诺）
1. **数据集构建**：从真实对话日志采样 → 标注 `(user_message, intents[], slots, session_scene, plan)`；脱敏；正负例；难例（ASR 错字、多意图、附件）。规模建议 ≥ 5k 条起步。
2. **教师标注**：用云端大模型（qwen-plus 级）批量产出候选 label，人工校验 → 蒸馏信号。
3. **SFT**：LoRA/QLoRA 微调 Qwen3-4B（PEFT），指令模板与线上 Router prompt 完全一致。
4. **评测集**：固定 500 条 golden set，报意图 macro-F1 / 槽位准确率 / 计划字段匹配率。
5. **蒸馏**：可用教师 logits 做 soft-label 蒸馏（可选，收益需实测）。

### 3.4 量化压缩与指标可达性（诚实评估）
| 目标 | 达成路径 | 现实说明 |
|---|---|---|
| 体积压缩 70% | FP16→Q4_K_M（约 28% 体积，即压缩 72%）；Q5_K_M 约 35%（压缩 65%） | **可达**，但注意：结构化输出任务推荐 Q5_K_M，与"压缩 70%"略有张力；建议以精度优先选 Q5_K_M（压缩约 65%），或接受 Q4_K_M 并加强评测 |
| 精度损失 <5% | 用 golden set 对比 FP16 与量化版的意图 macro-F1 | **需实测**；多源显示 GGUF Q5_K_M 保留 97-99% 质量，一般可达成；但不能仅凭论文承诺，必须本地跑分 |
| 首 token 700ms | KV Cache 复用 + 算子融合 + 线程调度 + 短 prompt + `/no_think` | **需实测**；受硬件影响极大，方案给出优化手段，不承诺具体数值 |

### 3.5 端侧部署（三选一，按环境）
| 运行时 | 适用 | 关键优化 |
|---|---|---|
| llama.cpp / llama-server | 通用、CPU/NVIDIA/Apple，OpenAI 兼容 `/v1` | `-ngl` 卸载层数、`--jinja`、`-c` 上下文、KV Cache 复用 |
| ONNX Runtime | 跨平台、需 INT8 量化模型 | 算子融合、ExecutionProvider、线程数调优 |
| MNN | 移动端优先 | 轻量、ARM 优化 |

### 3.6 云侧兜底降级（可用性保障）
```
IntentRecognizer.recognize():
  try: 端侧小模型推理
  except (超时/加载失败/输出非法/health=false):
      → 降级到云 API provider（同一 OpenAI 兼容协议，改 api_base）
  → 再失败：降级到"现有单意图路径"（开关级兜底）
```
- 双模切换即 `intent_config.provider: api | local`（已设计）。
- 降级全链路埋点（`intent.provider.fallback`），用于统计端侧可用性。

### 3.7 验收
- 提供 `scripts/eval_intent.py`：跑 golden set，输出 F1 / 延迟分布 / 量化前后对比。
- 提供 `scripts/bench_router.py`：P50/P95/P99 首 token 与端到端延迟。
- 指标以脚本实测报告为准，写入 `outputs/eval_report.json`（不入库）。

---

## 4. 模块③ 多 Agent 链路优化

### 4.1 关键路径拆分与优化手段
| 手段 | 落地做法 | 预期收益 |
|---|---|---|
| 并行预取 | Router 输出 plan 后，并行预取：历史摘要、参考材料、PromptPackage（三者本无依赖） | 隐藏 I/O 延迟 |
| 技能并行调用 | 二期：independent 技能并发（与①的 parallel 编排共用） | 技能级延迟叠加消除 |
| 流式返回 | 已有 `assistant_token`；确保 Manager 首 token 即推，不等全文 | 感知延迟 |
| 中间结果缓存 | PromptPackage 已有缓存（`_PROMPT_PACKAGE_CACHE`）；新增：路由结果缓存（相同输入指纹）、附件分析结果缓存（已有 `MessageBlockMemoryStore`） | 降重复计算 |
| 冗余上下文裁剪 | 复用 `MemoryProjector` 的 router profile 裁剪（已存在但未接线）；Responder 侧按 `prompt_context_policy` 裁剪 | 降 token 与 prefill 时间 |

### 4.2 P99 优化路径（5000→1500ms）
按 contribution 排序（需 profile 验证，非拍脑袋）：
1. Router 下沉端侧小模型（省一次云 API RTT，通常最大头）
2. `previous_response_id` 连续对话（省去重喂历史的 prefill 时间）——见 4.3
3. 并行预取 + PromptPackage 缓存命中
4. 上下文裁剪降 token
5. 动态选模（4.4）避免简单问题走大模型

> **诚实说明**：P99 1500ms 是激进目标，是否可达取决于硬件、云端 API 延迟、ASR/TTS 耗时。必须先建 profile 基线（`append_trace_log` 的 t0~t8 已有），逐项压测，不能靠改代码直接达成。

### 4.3 启用 `previous_response_id` 连续对话
**现状**：字段已在 `ConversationState`（:42-43）、持久化（:72-73）、更新（:586），但 `llm/README.md:58` 明确"不使用"，`build_request` 只发 instructions+input。

**落地**：
- 在 `llm_model_executor/service.py` 的 request 中，按配置开关附加 `previous_response_id`（Responses API 原生支持）。
- 每轮 `response.completed` 后回写 `responder_previous_response_id`。
- 与本地持久化配合：省去重复喂历史，但要处理"上下文快照一致性"（patch 后需 invalidate）。
- 风险：Responses API 的服务端会话与本地 turn_records 可能分叉，需定义"谁是对话事实源"（建议本地 turn_records 为准，服务端 id 仅作加速）。

### 4.4 动态模型选择
```
选模决策 = f(任务复杂度, 路由置信度, 分支/模块)
  - 简单 general_qa + 高置信 → 小模型（端侧/便宜云模型）
  - 教育解题/多模态 + 中置信 → 主大模型
  - 识别失败/低置信/工具调用失败 → 兜底大模型 / 澄清分支
```
落点：`inference_runtime/service.py` 的后端选择处（现有 `_should_use_agents_backend`，:45-66），扩展为 `_select_model_tier()`；决策全量埋点。

---

## 5. 模块④ 上下文工程（Context Compiler）

### 5.1 目标
统一编译层，把 `system / developer(runtime) / history / user` 编译为模型可见上下文，支持技能插件注入、运行时状态注入、历史裁剪、多模态拼装。

### 5.2 现状差距
`ContextCompiler`（`multi_turn_context_builder/compiler.py`）目前只有：
- `_normalize_user_message`（:82）：清洗 user block
- `_record_to_messages`（:162）：turn record → messages
- `build_conversation_context`（:188）：拼历史
- `build_router_input` / `build_responder_input`（:234/:245）

**缺**：system/developer 分层、记忆注入、技能注入、多模态拼装、按 profile 裁剪。

### 5.3 落地设计（在现有 compiler 上增强，不重写）
```python
def compile(profile: Literal["router","responder"], ctx, state, plan) -> CompiledContext:
    system   = load_skill_instructions(plan.prompt_package)      # 技能插件注入（已有 PromptPackage）
    developer = build_runtime_payload(                            # 运行时状态注入（本模块新增）
        scene=state.session_scene,
        education=state.memory.education_state,                  # 复用已有教育态
        memory_projection=state.memory.build_projection(profile),# 接线已有但未用的投影
    )
    history = select_history(ctx, max_messages, policy)           # 历史裁剪（已有基础）
    user    = assemble_multimodal(ctx.current)                    # 多模态拼装（已有 block 规范化）
    return CompiledContext(system, developer, history, user)
```
- 角色分层落到 Responses API：顶层 `instructions`=system+developer，`input`=[history..., user]（保持与现有 executor 兼容）。
- **关键接线点**：把"未接线孤岛"的 `MemoryProjector.build()` / `MemoryRetriever.retrieve()` 在此调用，记忆才真正生效。

### 5.4 验收
- 单测：四种 profile 输出的消息结构、历史裁剪边界、多模态 block 保留。
- 集测：注入教育态后，responder instructions 含正确教育上下文。

---

## 6. 模块⑤ 记忆与多模态延续

### 6.1 目标
双层记忆：`SessionMemory`（领域记忆聚合）+ `ConversationState`（会话事实源），以 `turn_records` 为事实源，沉淀用户事实槽位、近期主题、上下文/多模态摘要、教育态、附件分析缓存；解决"新附件误继承旧上下文"与"连续追问需保留视觉上下文"。

### 6.2 现状（骨架齐全，缺接线）
已存在（见 `domain/memory/ARCHITECTURE.md`）：
- `ConversationState.turn_records`（事实源）、`complete_realtime_turn`（两段式落盘）
- `SessionMemory` 聚合：`EducationMemory`（21 键）、`SummaryMemory`、`MessageBlockMemoryStore`（SHA256 key + 64 FIFO）、`MemoryRetriever`（固定 score）、`MemoryProjector`（router 裁剪）
- `MediaArtifact`（`domain/multimodal/media.py`）

**问题**：检索/投影/附件缓存 API 无生产调用点；`MediaArtifact` 主流程不用；`multimodal_context_summary` 与 `context_summary` 算法相同（名不副实）。

### 6.3 落地设计
| 能力 | 做法 |
|---|---|
| 事实槽位 | 在 `EducationMemory` 增 `user_facts: dict`（年龄/年级/偏好等），由 Agent patch（走白名单）写入 |
| 记忆接线 | 在 ContextCompiler（模块④）调用 `build_projection` / `retrieve_relevant_memories` |
| 附件摘要缓存 | 复用 `MessageBlockMemoryStore.remember_block_analysis`，在 `_decode_attachments` 后写入 |
| 引用继承判断 | 新增 `should_inherit_visual_context(current_blocks, last_visual_turn)`：有**新**图片/视频时清空旧视觉引用，纯文字追问时保留最近视觉摘要 |
| 上下文隔离 | 多模态 turn 记录 `context_isolation_token`，跨轮引用需 token 匹配 |

### 6.4 两类问题的对策
- **新附件误继承旧上下文** → 检测到新 artifact 时，`build_projection` 的 `message_block_memory` 只保留当前轮，不取历史。
- **连续追问需保留视觉上下文** → 纯文字 turn 且上一轮有视觉 artifact 时，把 `last_visual_summary` 注入 developer payload（标记来源 turn_id，避免无限继承）。

### 6.5 验收
- 单测：引用继承判断的真值表（新图/旧图/纯追问/跨场景）。
- 集测：两轮对话——第 1 轮传图问"这是什么"，第 2 轮"它多少钱"，验证视觉摘要被正确继承；再传新图验证旧摘要被清除。

---

## 7. 模块⑥ 实时交互与可观测性

### 7.1 现状（基本成品）
- ASR/LLM/TTS/WS 串联：`app.py:ws_audio` + `RealtimeConversationSession`（1409 行）已完整
- barge-in：服务端 `BargeInDetector` + `session.interrupt` 已实现
- 未完成 turn 上下文保留：`upsert_realtime_user_turn` 两段式已实现
- trace：`append_trace_log`；eval：`evaluation_logger.py`

### 7.2 需补强
| 项 | 做法 |
|---|---|
| 前端本地 barge-in 接线 | `app.js` 的 `maybeInterruptPlaybackFromMic()`(:752) 已实现但**未调用**；接入 worklet onmessage，并让 `interruptPlayback` 传递 reason（当前丢失） |
| `playback_started` 死消息 | 服务端 `app.py:680` 只 continue；接入 t8 时序统计 |
| 双播放路径去重 | 同一 PCM 同时走 FastRTC iframe + AudioContext，存在双出声风险；明确单一路径 |
| 可观测埋点扩展 | 新增：路由决策、模型选择（`_select_model_tier`）、上下文快照 hash、Agent 事件、patch 应用/拒绝、端云降级——统一 `append_trace_log` schema |
| eval 体系 | 把 golden set 评测结果写入 `evaluation.jsonl`，与线上 trace 关联，支撑策略迭代 |

### 7.3 trace schema 建议（统一字段）
```json
{
  "ts": "...", "turn_id": "...", "session_id": "...",
  "event": "route.decision | model.selected | context.snapshot | agent.event | state.patch.applied | intent.fallback",
  "actor": "router | manager | subagent:solve | recognizer",
  "payload": { "...": "事件相关数据" },
  "latency_ms": 0, "trace_id": "..."
}
```

---

## 8. 关键数据结构与目录变更总表

| 变更 | 类型 | 落点 | 关联模块 |
|---|---|---|---|
| `IntentItem` / `IntentsResult` / `ExecutionPlan` / `SubTask` / `SubAgentResult` | 新建 | `ava/intent/types.py` | ①②④ |
| `RouteDecision.intents` 扩展 | 改 | `ava/router_selector/schema.py` | ① |
| `TurnPlan.sub_tasks` 扩展 | 改 | `ava/inference_runtime/types.py` | ① |
| `AGENT_PATCH_WHITELIST` + patch apply | 新建 | `agent_backend.py` / Orchestrator | ① |
| `ava/intent/`（recognizer/providers/arbiter/orchestrator/prompts） | 新建 | 目录 | ①② |
| `scripts/eval_intent.py` / `bench_router.py` | 新建 | scripts/ | ②③ |
| `ContextCompiler.compile(profile)` | 增强 | `multi_turn_context_builder/compiler.py` | ④⑤ |
| `SessionMemory.user_facts` + 引用继承判断 | 增强 | `domain/memory/`、`domain/multimodal/` | ⑤ |
| trace schema 扩展 | 增强 | `core/tracing/`（现 `runtime/errors.py` 附近）+ 各处埋点 | ⑥ |
| `static/app.js` barge-in 接线 | 改 | static/ | ⑥ |

---

## 9. 分阶段 Roadmap（对齐前序 P0-P9，按依赖与风险排序）

| 阶段 | 内容 | 模块 | 风险 |
|---|---|---|---|
| **S0 配套底座** | 建 `tests/`、golden set 雏形、trace schema 统一、profile 基线脚本 | 全 | 低 |
| **S1 上下文接线** | ContextCompiler 增强 + 记忆投影/检索接线 + 多模态引用继承 | ④⑤ | 中（改 compiler） |
| **S2 多智能体骨架** | Intent 数据结构 + 串行 Orchestrator + 状态白名单 patch + 4 技能 Agent | ① | 中（改 agent_backend） |
| **S3 小模型双模** | API/local provider + 开关 + 云兜底降级 + 结构化输出 | ② | 中高（新推理链路） |
| **S4 链路优化** | previous_response_id 启用 + 并行预取 + 动态选模 + 缓存/裁剪 | ③ | 中 |
| **S5 端到端调优** | SFT/量化/部署 + 延迟压测 + 指标达成验证 | ②⑥ | 高（需数据/硬件） |
| **S6 可观测完善** | barge-in 接线、trace/eval 全埋点、灰度开关 | ⑥ | 低 |

> 建议先做 **S0→S1→S2**：这几步纯代码、可验证、不依赖训练数据，风险最低；S3 之后逐步引入模型与压测。

---

## 10. 指标可达性评估（不回避）

| 指标 | 能否靠代码直接达成 | 前置条件 | 结论 |
|---|---|---|---|
| 体积压缩 70% | ⚠️ 部分 | 选 Q4_K_M（压缩~72%）可达；但精度优先建议 Q5_K_M（~65%） | 需取舍 |
| 精度损失 <5% | ❌ | golden set + 量化后实测 | 需数据，验证后确认 |
| 首 token 700ms | ❌ | 端侧硬件 + KV Cache + 短 prompt | 需实机压测 |
| P99 5000→1500ms | ❌ | profile 基线 + 全链路优化 + 压测环境 | 激进目标，需逐项验证 |
| 能力类（架构/协议/编排/记忆接线/埋点） | ✅ | 按本文设计实现 | 可落地 |

**必须向干系人说明**：4 个 KPI 是**验收目标**，本方案提供达成路径与测量方法；在拿到真实数据、硬件与压测结果前，不应视为已承诺交付。

---

## 11. 风险与待确认问题

### 11.1 风险
- **文档与代码双重滞后**：README 与真实代码已分叉，方案中的"现状"以代码为准；建议在 S0 同步校正 README。
- **改动面广**：`session.py`(1409) 与 `agent_backend.py` 耦合深，S2/S4 集成需谨慎。
- **指标不可证伪**：无评测集/压测环境时，KPI 无法验证——S0 是刚需，不是可选项。
- **模型分叉**：本地 turn_records（事实源）与服务端 previous_response_id（加速）可能不一致，需定义仲裁规则。

### 11.2 待确认（请评审）
1. "3B" 是否坚持？还是沿用已调研的 Qwen3-4B（更强）？
2. 端侧运行时优先级：llama.cpp / ONNX Runtime / MNN，目标设备是什么（有无 GPU/NPU）？
3. 压缩 70% 与精度 <5% 冲突时，优先级如何？（建议精度优先）
4. 云端大模型最终选型（qwen-plus / glm / 其他）与预算？
5. SFT 数据来源与标注资源（谁提供脱敏日志、谁标注）？
6. previous_response_id 与服务端会话，谁为事实源？（建议本地优先）
7. 技能子 Agent 是否包含"学情评估 assess"的新 Skill 资产（需新建 prompt-plugin/components/task/assess）？
8. 6 大模块的落地顺序是否认可 S0→S1→S2→S3→S4→S5→S6？

---

## 附注：本轮与后续的工作边界
- 本轮产出：本方案文档 + 前序已完成的 README 修复、API Key 治理、多意图子 Agent 方案。
- 后续进入 S0/S1 时再逐模块改代码，每阶段附单测与验收。
- `.idea/workspace.xml` 的改动是 IDE 自动生成，非业务改动。
