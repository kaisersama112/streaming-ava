"""路由 SFT 微调流水线（可跑通验证，默认仅 smoke 步数，不做完整训练）。

用路由数据集对剪枝后视觉小模型做 assistant-only loss 的 SFT 步骤，验证训练链路可跑通。
默认 --max-steps 2、冻结除最后一层外的参数（控制 CPU 内存），默认不覆盖部署模型；
仅当显式 --save 时保存到独立 --out 目录。多模态完整训练不在本流水线范围（按需扩展 processor）。
用法: python edge_router/recover_sft.py [--max-steps N] [--save --out DIR]
"""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODELS = ROOT / "models"
DATA = ROOT.parent / "data" / "router_sft_train.jsonl"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=str(MODELS / "router-pruned-hf"))
    ap.add_argument("--data", default=str(DATA))
    ap.add_argument("--epochs", type=int, default=1)
    ap.add_argument("--max-steps", type=int, default=2, help="smoke 步数上限，证明流水线可跑通")
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--max-len", type=int, default=256)
    ap.add_argument("--accum", type=int, default=1)
    ap.add_argument("--save", action="store_true", help="显式保存（默认不保存，不覆盖部署模型）")
    ap.add_argument("--out", default=str(MODELS / "router-sft-demo"))
    args = ap.parse_args()

    import torch
    from transformers import AutoProcessor

    from prune_router import load_model, language_layers

    torch.set_num_threads(12)
    model, _ = load_model(args.model)
    proc = AutoProcessor.from_pretrained(args.model)
    tok = proc.tokenizer

    # 冻结除最后一层语言层 + lm_head 外的参数，控制 AdamW 优化器状态内存。
    for p in model.parameters():
        p.requires_grad_(False)
    last = language_layers(model)[-1]
    for p in last.parameters():
        p.requires_grad_(True)
    if hasattr(model, "lm_head"):
        for p in model.lm_head.parameters():
            p.requires_grad_(True)
    trainable = [p for p in model.parameters() if p.requires_grad]
    model.train()

    from dataio import load_records

    samples = load_records(args.data)
    opt = torch.optim.AdamW(trainable, lr=args.lr)
    losses, step = [], 0
    done = False
    for epoch in range(args.epochs):
        for sample in samples:
            if step >= args.max_steps:
                done = True
                break
            msgs = sample["messages"]
            prompt_msgs = [m for m in msgs if m["role"] != "assistant"]
            full = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=False)
            prompt = tok.apply_chat_template(prompt_msgs, tokenize=False, add_generation_prompt=True)
            ids = tok(full, return_tensors="pt", truncation=True, max_length=args.max_len)["input_ids"]
            plen = len(tok(prompt, truncation=True, max_length=args.max_len)["input_ids"])
            labels = ids.clone()
            labels[:, :plen] = -100
            out = model(input_ids=ids, labels=labels)
            out.loss.backward()
            step += 1
            if step % args.accum == 0:
                opt.step()
                opt.zero_grad()
            losses.append(float(out.loss.detach()))
            print(f"step {step} loss {losses[-1]:.4f}", flush=True)
        if done:
            break
    opt.step()
    opt.zero_grad()
    model.eval()

    saved = False
    if args.save:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        model.save_pretrained(str(out))
        proc.save_pretrained(str(out))
        saved = True
    report = {"steps": step, "max_steps": args.max_steps,
              "trainable_params": sum(p.numel() for p in trainable),
              "first_loss": losses[0] if losses else None,
              "last_loss": losses[-1] if losses else None,
              "saved": saved, "out": args.out if saved else ""}
    (ROOT / "recover_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report), flush=True)
    print("RECOVER_OK", flush=True)


if __name__ == "__main__":
    main()