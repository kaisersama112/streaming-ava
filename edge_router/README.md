# edge_router —— 端侧路由小模型（剪枝 / 量化 / 部署 / 评测 / 正负样本微调）

本目录是「端云协同」中**端侧小模型**的完整实施区：把高频意图路由下沉到本地小模型，
复杂生成与低置信路由交由云侧大模型（DeepSeek）兜底。支持**多模态**（视觉基座 Qwen2-VL）。

> 主服务通过 `configs/config.local.yaml` 的 `intent_config`（`provider: local`）接入本目录部署的
> OpenAI 兼容服务；路由先走端侧，超时 / 异常 / 低置信自动降级云侧（见 `ava/router_selector/edge_cloud.py`
> 与 `service.py:_execute_route`）。

---

## 1. 目录与脚本

| 脚本 | 职责 |
|---|---|
| `download_vlm.py` | 下载视觉基座 `Qwen/Qwen2-VL-2B-Instruct`（带重试，走默认 HF） |
| `download_models.py` | 下载文本小模型 `Qwen/Qwen2.5-0.5B-Instruct` |
| `prune_router.py` | 语言解码层**深度剪枝**（均匀选层、保留首尾层与视觉塔） |
| `quantize_router.py` | 语言层 Linear **动态 INT8 量化**（视觉塔保持 fp32） |
| `serve_local.py` | OpenAI 兼容本地推理服务（真流式 + KV cache；`--no-quantize` 起 fp32 基线） |
| `build_mm_dataset.py` | 合成**多模态**路由数据集（PIL 图片 artifact + 路由标签） |
| `build_posneg_dataset.py` | 构建**正负样本对**（正确路由 vs 扰动错误路由） |
| `sft_posneg.py` | **正负样本微调**（contrastive margin / DPO） |
| `recover_sft.py` | assistant-only SFT 流水线（smoke 可跑通验证） |
| `eval_router.py` | **性能 + 效果**评估（体积/压缩/延迟/吞吐 + 路由准确率/精度损失） |
| `dataio.py` | 鲁棒数据加载（兼容 JSON 数组 / JSONL / 拼接 JSON 流） |
| `serve_edge.py` | 早期 llama.cpp 服务入口（已弃用，llama-cpp-python 在 Windows 长路径下不可安装） |

产物目录：`models/`（基座与剪枝/量化模型）、`prune_report.json`、`quantize_report.json`、
`eval_report.json`、`posneg_report.json`、`recover_report.json`。

---

## 2. 环境准备

```bash
# 项目根目录，使用 .venv（Python 3.11）
pip install torch transformers fastapi uvicorn httpx pillow
# CPU 版 torch 即可（本机 torch 2.15.0+cpu / 12 核）
```

> llama.cpp / MNN / ONNX Runtime 路线说明：`llama-cpp-python` 仅有 sdist，在 Windows 长路径下
> 解压失败（`ChatAttachmentsListItemMcpPrompt.svelte` OSError），故改用纯 Python 的
> torch + transformers 动态量化路线，无需编译 C++。

---

## 3. 完整操作命令（按顺序）

### 3.1 下载基座

```bash
python edge_router/download_vlm.py        # Qwen2-VL-2B-Instruct -> models/qwen2-vl-2b-instruct
python edge_router/download_models.py     # Qwen2.5-0.5B-Instruct -> models/qwen2.5-0.5b-instruct
```

### 3.2 剪枝（语言层深度剪枝，保留视觉塔）

```bash
# 视觉基座 28 -> 24 层（轻剪枝 ~14%，无需微调即可保持结构可用）
python edge_router/prune_router.py --base edge_router/models/qwen2-vl-2b-instruct \
    --out edge_router/models/router-pruned-hf --keep-layers 24

# 文本小模型 24 -> 22 层（可选，用于高频文本路由）
python edge_router/prune_router.py --base edge_router/models/qwen2.5-0.5b-instruct \
    --out edge_router/models/router-0p5b-pruned-hf --keep-layers 22
```

- Qwen2-VL 语言层位于 `model.model.language_model.layers`，层数 / `layer_types` 在 `config.text_config`；
  纯文本模型位于 `model.model.layers`。脚本用 `language_layers()` / `set_num_layers()` 自动适配。
- 输出 `prune_report.json`：`base_layers / kept_layers / kept_indices / layer_prune_ratio /
  base_params / pruned_params / param_prune_ratio / vision_tower_preserved`。

### 3.3 量化（语言层 INT8，视觉塔 fp32）

```bash
python edge_router/quantize_router.py --pruned edge_router/models/router-pruned-hf \
    --out edge_router/models/router-pruned-int8
```

- `torch.ao.quantization.quantize_dynamic(lang, {torch.nn.Linear}, dtype=torch.qint8)`。
- 量化权重以 `packed_params` 存储，`parameters()` 不计入体积；压缩比按**落盘文件 size** 计算。
- 输出 `quantize_report.json`：`language_fp32_bytes / language_int8_bytes / compression_vs_fp32`。
- 保存 `pytorch_model.int8.bin` + `config` + `processor`；部署时重新量化语言层并
  `load_state_dict(..., weights_only=True)` 载入。

### 3.4 部署本地服务

端云协同采用**双端口分工**：路由端口承担高频意图路由（端侧优先 + 云兜底），
视觉端口承担 image→text 分析（供 `ensure_visual_analysis` 缓存复用）。

```bash
# 路由服务（:8080）：剪枝 + INT8 视觉小模型，文本 + 图片
python edge_router/serve_local.py --threads 12 --port 8080

# 视觉服务（:8081）：基座 2B VL 仅 INT8（不做深度剪枝，保留视觉质量）
python edge_router/quantize_router.py --pruned edge_router/models/qwen2-vl-2b-instruct \
    --out edge_router/models/router-vision-int8
python edge_router/serve_local.py --pruned edge_router/models/qwen2-vl-2b-instruct \
    --int8 edge_router/models/router-vision-int8 --port 8081 --threads 6 \
    --model-name qwen2-vl-2b-local

# 未量化 fp32 基线（:8082，用于精度损失对比）
python edge_router/serve_local.py --no-quantize --port 8082 \
    --model-name qwen2-vl-2b-pruned-fp32-router
```

主服务通过环境变量把视觉分析指向视觉端口：
`STREAMING_AVA_EDGE_VISION_API_BASE=http://127.0.0.1:8081/v1`
（见 `ava/domain/multimodal/edge_vision.py`）。路由端口仍由 `intent_config.local.api_base` 指定。

> 说明：深度剪枝会显著削弱小模型指令跟随（实测剪枝 2B 路由输出退化），
> 因此**视觉分析用未剪枝基座 + INT8** 保证 image→text 质量；
> 路由端侧输出退化 / 低置信 / 超时由云侧 DeepSeek 兜底，保证生产正确性。

接口：`GET /health`、`GET /v1/models`、`POST /v1/chat/completions`（支持 `stream`、`image_url`/`input_image`）。
真流式用 `TextIteratorStreamer`，`use_cache=True` 复用 KV cache，`torch.set_num_threads(N)` 调度线程。

### 3.5 构建数据集（含多模态 + 正负样本）

```bash
python edge_router/build_mm_dataset.py       # data/mm_images/*.png + router_golden_mm.jsonl + router_sft_train_mm.jsonl
python edge_router/build_posneg_dataset.py   # data/router_sft_posneg.jsonl + router_sft_posneg_mm.jsonl
```

### 3.6 正负样本微调（核心方法，见 §5）

```bash
# smoke 验证链路可跑通（默认 2 步，不保存、不覆盖部署模型）
python edge_router/sft_posneg.py --loss margin --max-steps 2

# 真正训练并保存到独立目录（按需放大步数 / 换基座）
python edge_router/sft_posneg.py --loss margin --max-steps 200 --save \
    --out edge_router/models/router-posneg

# DPO（带冻结参考模型，内存翻倍，建议小模型 / GPU）
python edge_router/sft_posneg.py --loss dpo --beta 0.1 --max-steps 200 --save
```

### 3.7 评估（性能 + 效果）

```bash
# 量化模型评估（文本 + 多模态金标）
python edge_router/eval_router.py --api-base http://127.0.0.1:8080/v1

# 与未量化基线对比，计算精度损失（目标 <5%）
python edge_router/eval_router.py --api-base http://127.0.0.1:8080/v1 \
    --base-api-base http://127.0.0.1:8081/v1
```

输出 `eval_report.json`，详见 §6。

---

## 4. 端云协同接入

`configs/config.local.yaml`（gitignored）：

```yaml
intent_config:
  enabled: true
  provider: local
  cloud_fallback_enabled: true
  min_confidence: 0.6
  cache: { enabled: true, ttl_seconds: 120 }
  local:
    runtime: torch_int8
    api_base: "http://127.0.0.1:8080/v1"
    model: "qwen2-vl-2b-pruned-int8-router"
    timeout_ms: 1500
    threads: 12
    kv_cache_reuse: true
```

路由执行（`ava/router_selector/service.py:_execute_route`）：端侧请求经 `build_edge_request_context`
改写 metadata（api_base/api_key/timeout/provider=edge_local）→ 端侧推理 → 解析 JSON →
置信度 ≥ `min_confidence` 则采用，否则 / 超时 / 异常降级云侧 DeepSeek，降级原因落 trace。

多模态：图片在 turn intake 经 `ava/domain/multimodal/edge_vision.py:ensure_visual_analysis`
调用端侧视觉能力生成 image→text 摘要并缓存，路由 / 意图 / 主干共享，避免重复视觉推理。

---

## 5. 正负样本微调方法

**动机**：只模仿正样本（普通 SFT）无法让模型学会「拒绝错误路由」。正负样本微调在同一 prompt 下
同时给出正样本（正确路由 JSON）与负样本（场景 / 意图 / 模块错配、但同样「自信」的错误 JSON），
显式拉开二者似然差距。

**负样本构造**（`build_posneg_dataset.py`）：对每条正样本，按 `turn_scene` 映射到一个 plausible 的错误对照
（education→general_qa、general_qa→education、casual_chat→education、clarify→general_qa），
同步改写 `session_scene / turn_scene / intent / plan.module / plan.subject`，`confidence` 仍设 0.9，
迫使模型靠语义而非置信度区分。

**损失**（`sft_posneg.py`，`mean_logπ` 为 completion 段平均 token 对数似然）：

- `margin`（默认，单模型）：
  `L = w_sft·(-mean_logπ(pos)) + w_margin·max(0, margin - (mean_logπ(pos) - mean_logπ(neg)))`
  SFT 锚定项保证正样本仍可生成，margin 项拉开正负差距。
- `dpo`（带冻结参考模型）：
  `L = -log σ(β·((logπ(pos)-logπ_ref(pos)) - (logπ(neg)-logπ_ref(neg))))`

**工程约束**：默认 `--max-steps 2` 仅证明链路可跑通（不做完整训练）；冻结除最后一层 + `lm_head` 外参数
以控制 CPU 上 AdamW 优化器状态内存；默认不保存、不覆盖部署模型，`--save` 时写入独立 `--out`。
多模态正负样本对（`router_sft_posneg_mm.jsonl`）已生成，视觉基座 + processor 扩展即可训练。

---

## 6. 评估指标

`eval_router.py` 同时量化**性能**与**效果**：

性能：
- 模型落盘体积、语言层压缩比（`quantize_report.compression_vs_fp32`）、层剪枝率 / 参数剪枝率。
- 首 token 延迟 p50 / p99 / mean、总延迟 p50 / p99、平均 tokens/s。

效果：
- `turn_scene / intent / plan.module` 字段准确率、整体精确匹配率、JSON 可解析率。
- 文本金标（`router_golden.jsonl`）与多模态金标（`router_golden_mm.jsonl`）分开统计。
- 量化 vs 未量化基线的准确率差值（`accuracy_drop_vs_base`，目标 <5%）。

### 当前实测（CPU，12 线程，仅供参考）

| 指标 | 值 |
|---|---|
| 视觉基座层数 | 28 → 24（`layer_prune_ratio` 0.1429） |
| 参数量 | 2,208,985,600 → 2,021,794,304（`param_prune_ratio` 0.0847，视觉塔保留） |
| 语言层 fp32 → INT8 | 4,492,591,104 B → 1,123,744,049 B（**压缩 74.99%**） |

> 延迟与准确率以 `eval_report.json` 实跑结果为准。2B 视觉模型在纯 CPU 上首 token / 总延迟较高，
> 更适合一次性图片→文本视觉分析（缓存复用）；高频文本路由建议用 0.5B 小模型，
> 复杂 / 低置信路由由云侧兜底。剪枝会削弱指令跟随，正负样本微调用于恢复路由判别力。

---

## 7. 安全

- 真实密钥不入库；端侧 `api_key` 留空，云侧密钥经 gitignored `*.local.yaml` / 环境变量注入。
- `torch.load` 一律 `weights_only=True`。