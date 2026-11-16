"""下载端侧路由小模型（HF safetensors，供剪枝）与端侧视觉模型（GGUF，供多模态分析）。"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODELS = ROOT / "models"
MODELS.mkdir(parents=True, exist_ok=True)

from huggingface_hub import hf_hub_download, snapshot_download, HfApi

# 1) 路由小模型：Qwen2.5-0.5B-Instruct（24 层，供深度剪枝 + 量化）
text_dir = MODELS / "qwen2.5-0.5b-instruct"
print("downloading router base weights ...", flush=True)
snapshot_download(
    "Qwen/Qwen2.5-0.5B-Instruct",
    local_dir=str(text_dir),
    allow_patterns=["*.json", "*.safetensors", "*.txt", "tokenizer*"],
)
print("router base done:", text_dir, flush=True)

# 2) 端侧视觉模型：Qwen2-VL-2B-Instruct GGUF（q4_k_m）+ mmproj（F16）
vlm_dir = MODELS / "qwen2-vl-2b-gguf"
vlm_dir.mkdir(parents=True, exist_ok=True)
api = HfApi()
files = api.list_repo_files("Qwen/Qwen2-VL-2B-Instruct-GGUF")
gguf = [f for f in files if f.endswith(".gguf")]
main = [f for f in gguf if "mmproj" not in f.lower() and "q4_k_m" in f.lower()]
mmproj = [f for f in gguf if "mmproj" in f.lower() and ("f16" in f.lower() or "fp16" in f.lower())]
if not main:
    main = [f for f in gguf if "mmproj" not in f.lower() and "q4" in f.lower()]
if not mmproj:
    mmproj = [f for f in gguf if "mmproj" in f.lower()]
pick = (main[:1] + mmproj[:1])
print("vlm picks:", pick, flush=True)
for fname in pick:
    hf_hub_download("Qwen/Qwen2-VL-2B-Instruct-GGUF", fname, local_dir=str(vlm_dir))
print("vlm done:", vlm_dir, flush=True)
print("ALL_DOWNLOADS_OK", flush=True)