"""端侧路由模型 INT8 量化（torch 动态量化，仅语言解码层，保留视觉塔 fp32）。

对剪枝后的 Qwen2-VL 模型的语言层 Linear 做 qint8 动态量化，保存量化 state_dict +
config + processor。体积压缩比写入 quantize_report.json。无需编译 C++。
用法: python edge_router/quantize_router.py [--pruned DIR] [--out DIR]
"""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODELS = ROOT / "models"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pruned", default=str(MODELS / "router-pruned-hf"))
    ap.add_argument("--out", default=str(MODELS / "router-pruned-int8"))
    args = ap.parse_args()

    import torch
    from transformers import AutoConfig, AutoProcessor

    from prune_router import load_model, language_layers

    print("loading pruned vision model ...", flush=True)
    model, cfg = load_model(args.pruned)
    proc = AutoProcessor.from_pretrained(args.pruned)

    lang = language_layers(model)
    fp32_bytes = sum(p.numel() * p.element_size() for p in lang.parameters())
    quantized = torch.ao.quantization.quantize_dynamic(lang, {torch.nn.Linear}, dtype=torch.qint8)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    bin_path = out / "pytorch_model.int8.bin"
    torch.save(quantized.state_dict(), bin_path)
    model.config.save_pretrained(str(out))
    proc.save_pretrained(str(out))
    # 量化后权重以 packed_params 存储，parameters() 不计入；用落盘文件size衡量真实体积。
    int8_bytes = bin_path.stat().st_size

    report = {
        "scheme": "torch dynamic INT8 (language Linear->qint8, vision tower fp32)",
        "language_fp32_bytes": fp32_bytes,
        "language_int8_bytes": int8_bytes,
        "compression_vs_fp32": round(1 - int8_bytes / fp32_bytes, 4),
        "output": str(out),
    }
    (ROOT / "quantize_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False), flush=True)
    print("QUANTIZE_OK", flush=True)


if __name__ == "__main__":
    main()