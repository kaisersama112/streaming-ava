"""路由小模型「正负样本」微调流水线（contrastive / preference SFT，可跑通验证）。

方法：同一 prompt 下给出正样本（正确路由 JSON）与负样本（错误路由 JSON），
让模型学会「抬高正样本 completion 似然、压低负样本似然」，而非只模仿正样本。

损失（--loss）：
- margin（默认，单模型）：L = w_sft·(-mean_logπ(pos)) + w_margin·max(0, margin - (mean_logπ(pos) - mean_logπ(neg)))
  其中 mean_logπ 为 completion 段平均 token 对数似然；SFT 锚定项保证正样本仍可生成。
- dpo（需参考模型）：L = -log σ(β·((logπ(pos)-logπ_ref(pos)) - (logπ(neg)-logπ_ref(neg))))
  参考模型为训练前冻结副本（内存翻倍，建议小模型 / GPU）。

默认仅 smoke 步数（--max-steps 2）、冻结除最后一层 + lm_head 外参数以控制 CPU 内存，
默认不覆盖部署模型；仅 --save 时保存到独立 --out。多模态正负样本对见 router_sft_posneg_mm.jsonl
（视觉基座 + processor 扩展即可训练，本流水线默认走文本对证明链路可跑通）。
用法: python edge_router/sft_posneg.py [--loss margin|dpo] [--max-steps N] [--save --out DIR]
"""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODELS = ROOT / "models"
DATA = ROOT.parent / "data" / "router_sft_posneg.jsonl"


def _completion_score(model, tok, prompt_msgs, completion, max_len):
    import torch

    prompt = tok.apply_chat_template(prompt_msgs, tokenize=False, add_generation_prompt=True)
    full = prompt + completion + (tok.eos_token or "")
    p_ids = tok(prompt, return_tensors="pt", truncation=True, max_length=max_len).input_ids
    f_ids = tok(full, return_tensors="pt", truncation=True, max_length=max_len).input_ids
    plen = int(p_ids.shape[1])
    if int(f_ids.shape[1]) <= plen:
        return None
    logits = model(input_ids=f_ids).logits[0, :-1]
    logp = torch.log_softmax(logits, dim=-1)
    targets = f_ids[0, 1:]
    token_logp = logp.gather(1, targets.unsqueeze(1)).squeeze(1)
    return token_logp[plen - 1:].mean()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=str(MODELS / "qwen2.5-0.5b-instruct"))
    ap.add_argument("--data", default=str(DATA))
    ap.add_argument("--loss", choices=["margin", "dpo"], default="margin")
    ap.add_argument("--max-steps", type=int, default=2)
    ap.add_argument("--epochs", type=int, default=1)
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--max-len", type=int, default=256)
    ap.add_argument("--margin", type=float, default=0.5)
    ap.add_argument("--w-sft", type=float, default=0.5)
    ap.add_argument("--w-margin", type=float, default=1.0)
    ap.add_argument("--beta", type=float, default=0.1)
    ap.add_argument("--save", action="store_true")
    ap.add_argument("--out", default=str(MODELS / "router-posneg-demo"))
    args = ap.parse_args()

    import copy
    import torch
    from transformers import AutoTokenizer

    from prune_router import load_model, language_layers

    torch.set_num_threads(12)
    model, _ = load_model(args.base)
    tok = AutoTokenizer.from_pretrained(args.base)
    model.train()

    ref_model = None
    if args.loss == "dpo":
        ref_model = copy.deepcopy(model).eval()
        for p in ref_model.parameters():
            p.requires_grad_(False)

    for p in model.parameters():
        p.requires_grad_(False)
    for p in language_layers(model)[-1].parameters():
        p.requires_grad_(True)
    if hasattr(model, "lm_head"):
        for p in model.lm_head.parameters():
            p.requires_grad_(True)
    trainable = [p for p in model.parameters() if p.requires_grad]
    opt = torch.optim.AdamW(trainable, lr=args.lr)

    from dataio import load_records

    pairs = load_records(args.data)
    rows, step, done = [], 0, False
    for epoch in range(args.epochs):
        for pair in pairs:
            if step >= args.max_steps:
                done = True
                break
            pm = pair["prompt_messages"]
            sp = _completion_score(model, tok, pm, pair["positive"], args.max_len)
            sn = _completion_score(model, tok, pm, pair["negative"], args.max_len)
            if sp is None or sn is None:
                continue
            if args.loss == "margin":
                gap = sp - sn
                loss = args.w_sft * (-sp) + args.w_margin * torch.relu(args.margin - gap)
                extra = {"gap": float(gap.detach())}
            else:
                with torch.no_grad():
                    rp = _completion_score(ref_model, tok, pm, pair["positive"], args.max_len)
                    rn = _completion_score(ref_model, tok, pm, pair["negative"], args.max_len)
                logits = (sp - rp) - (sn - rn)
                loss = -torch.nn.functional.logsigmoid(args.beta * logits)
                extra = {"dpo_logit": float(logits.detach())}
            loss.backward()
            opt.step()
            opt.zero_grad()
            step += 1
            rows.append({"step": step, "loss": float(loss.detach()),
                         "score_pos": float(sp.detach()), "score_neg": float(sn.detach()), **extra})
            print(f"step {step} loss {rows[-1]['loss']:.4f} pos {rows[-1]['score_pos']:.3f} neg {rows[-1]['score_neg']:.3f}", flush=True)
        if done:
            break

    model.eval()
    saved = False
    if args.save:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        model.save_pretrained(str(out))
        tok.save_pretrained(str(out))
        saved = True
    report = {"method": f"posneg-{args.loss}", "steps": step, "max_steps": args.max_steps,
              "trainable_params": sum(p.numel() for p in trainable),
              "first": rows[0] if rows else None, "last": rows[-1] if rows else None,
              "saved": saved, "out": args.out if saved else ""}
    (ROOT / "posneg_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False), flush=True)
    print("POSNEG_SFT_OK", flush=True)


if __name__ == "__main__":
    main()