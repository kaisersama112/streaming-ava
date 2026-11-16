"""端侧路由小模型深度剪枝（layer pruning），基座为视觉模型 Qwen2-VL-2B-Instruct。

仅剪语言解码层（保留视觉塔以支持多模态意图），均匀选层并保留首尾层。
默认 28 -> 24 层（轻剪枝 ~14%，无需微调即可保持可用）。剪枝率/参数量写入 prune_report.json。
用法: python edge_router/prune_router.py [--base DIR] [--out DIR] [--keep-layers N]
"""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODELS = ROOT / "models"


def count_params(model):
    return sum(p.numel() for p in model.parameters())


def language_layers(model):
    """Qwen2-VL 语言层在 model.language_model.layers；纯文本模型在 model.layers。"""
    inner = model.model
    lm = getattr(inner, "language_model", None)
    return (lm if lm is not None else inner).layers


def set_num_layers(model, n):
    cfg = model.config
    text_cfg = getattr(cfg, "text_config", None)
    target = text_cfg if text_cfg is not None else cfg
    target.num_hidden_layers = n
    lt = getattr(target, "layer_types", None)
    return target, lt


def load_model(base):
    import torch
    from transformers import AutoConfig, AutoModelForCausalLM

    cfg = AutoConfig.from_pretrained(base)
    if getattr(cfg, "model_type", "") == "qwen2_vl":
        from transformers import Qwen2VLForConditionalGeneration

        return Qwen2VLForConditionalGeneration.from_pretrained(base, torch_dtype=torch.float32), cfg
    return AutoModelForCausalLM.from_pretrained(base, torch_dtype=torch.float32), cfg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=str(MODELS / "qwen2-vl-2b-instruct"))
    ap.add_argument("--out", default=str(MODELS / "router-pruned-hf"))
    ap.add_argument("--keep-layers", type=int, default=24)
    args = ap.parse_args()

    import torch
    from transformers import AutoTokenizer, AutoProcessor

    print("loading base (vision) model ...", flush=True)
    model, cfg = load_model(args.base)
    try:
        tok = AutoProcessor.from_pretrained(args.base)
    except Exception:
        tok = AutoTokenizer.from_pretrained(args.base)
    base_params = count_params(model)
    layers = language_layers(model)
    L = len(layers)
    K = max(2, min(args.keep_layers, L))
    idx = sorted({round(i * (L - 1) / (K - 1)) for i in range(K)})
    print(f"depth prune language layers: {L} -> {len(idx)}, kept={idx}", flush=True)
    import torch as _torch
    layers_parent = layers
    new_layers = _torch.nn.ModuleList([layers_parent[i] for i in idx])
    inner = model.model
    lm = getattr(inner, "language_model", None)
    if lm is not None:
        lm.layers = new_layers
    else:
        inner.layers = new_layers
    target, layer_types = set_num_layers(model, len(idx))
    if isinstance(layer_types, list) and len(layer_types) == L:
        target.layer_types = [layer_types[i] for i in idx]
    pruned_params = count_params(model)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(out))
    tok.save_pretrained(str(out))

    report = {
        "base": args.base,
        "base_layers": L,
        "kept_layers": len(idx),
        "kept_indices": idx,
        "layer_prune_ratio": round(1 - len(idx) / L, 4),
        "base_params": base_params,
        "pruned_params": pruned_params,
        "param_prune_ratio": round(1 - pruned_params / base_params, 4),
        "vision_tower_preserved": True,
    }
    (ROOT / "prune_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False), flush=True)
    print("PRUNE_OK", flush=True)


if __name__ == "__main__":
    main()