"""补下载端侧视觉模型（transformers 格式 Qwen2-VL-2B-Instruct，HF 镜像防 SSL 中断）。"""
import os
import time
from pathlib import Path

os.environ.pop("HF_ENDPOINT", None)  # 默认 huggingface.co（镜像 SSL 不稳定）
from huggingface_hub import snapshot_download

ROOT = Path(__file__).resolve().parent
out = ROOT / "models" / "qwen2-vl-2b-instruct"
for attempt in range(5):
    try:
        print(f"attempt {attempt+1}: downloading Qwen2-VL-2B-Instruct ...", flush=True)
        snapshot_download(
            "Qwen/Qwen2-VL-2B-Instruct",
            local_dir=str(out),
            allow_patterns=["*.json", "*.safetensors", "*.txt", "tokenizer*", "preprocessor*"],
            max_workers=1,
        )
        print("VLM_DOWNLOAD_OK", flush=True)
        break
    except Exception as exc:
        print(f"attempt {attempt+1} failed: {type(exc).__name__}", flush=True)
        time.sleep(3)
else:
    raise SystemExit("VLM_DOWNLOAD_FAILED")