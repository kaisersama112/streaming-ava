"""端侧路由模型评估：性能（体积/压缩/延迟/吞吐）+ 效果（路由准确率）。

对本地部署的剪枝+INT8 视觉小模型（OpenAI 兼容服务）跑金标集：
- 性能：模型落盘体积、语言层压缩比、首 token p50/p99、总延迟 p50/p99、tokens/s。
- 效果：turn_scene / intent / plan.module 字段准确率与整体精确匹配率，文本与多模态分开统计。
- 量化精度损失：可选 --base-api-base 指向未量化基线服务，计算准确率差值（目标 <5%）。

结果写入 edge_router/eval_report.json。
用法:
  python edge_router/eval_router.py [--api-base URL] [--base-api-base URL] [--limit N]
"""
import argparse
import json
import statistics
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT.parent / "data"


def _system_prompt():
    from dataio import first_system_prompt

    return first_system_prompt(DATA / "router_sft_train.jsonl")


def _pct(values, p):
    if not values:
        return None
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(round((p / 100.0) * (len(s) - 1)))))
    return round(s[k], 2)


def _call(api_base, model, system, text, image, max_tokens):
    import httpx

    content = [{"type": "text", "text": text}]
    if image:
        content.append({"type": "image_url", "image_url": {"url": image}})
    payload = {"model": model, "messages": [
        {"role": "system", "content": system},
        {"role": "user", "content": content},
    ], "max_tokens": max_tokens, "stream": True, "temperature": 0}
    started = time.monotonic()
    first_ms, pieces, ntok = None, [], 0
    with httpx.Client(timeout=120, trust_env=False) as client:
        with client.stream("POST", f"{api_base.rstrip('/')}/chat/completions", json=payload) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                delta = (chunk.get("choices") or [{}])[0].get("delta", {})
                piece = delta.get("content")
                if piece:
                    if first_ms is None:
                        first_ms = round((time.monotonic() - started) * 1000, 2)
                    pieces.append(piece)
                    ntok += 1
    total_ms = round((time.monotonic() - started) * 1000, 2)
    raw = "".join(pieces)
    parsed, perr = {}, ""
    try:
        t = raw.strip()
        a, b = t.find("{"), t.rfind("}")
        parsed = json.loads(t[a:b + 1]) if a != -1 and b > a else json.loads(t)
    except Exception as exc:
        perr = str(exc)
    if not isinstance(parsed, dict):
        perr = perr or f"non-object output: {type(parsed).__name__}"
        parsed = {}
    return {"first_ms": first_ms, "total_ms": total_ms, "ntok": ntok,
            "raw": raw, "parsed": parsed, "parse_error": perr}


def _score(parsed, expected):
    plan = parsed.get("plan") or {}
    pred = {"turn_scene": parsed.get("turn_scene"), "intent": parsed.get("intent"),
            "module": plan.get("module") or plan.get("mode")}
    hits = {k: (str(pred.get(k)) == str(expected.get(k))) for k in expected}
    return pred, hits, all(hits.values())


def _eval_set(api_base, model, system, items, max_tokens):
    firsts, totals, tps = [], [], []
    field_hits = {"turn_scene": 0, "intent": 0, "module": 0}
    exact, parsed_ok, rows = 0, 0, []
    for it in items:
        try:
            r = _call(api_base, model, system, it["text"], it.get("image"), max_tokens)
        except Exception as exc:
            rows.append({"id": it["id"], "error": str(exc)})
            continue
        if r["first_ms"] is not None:
            firsts.append(r["first_ms"])
        totals.append(r["total_ms"])
        if r["ntok"] and r["total_ms"]:
            tps.append(round(r["ntok"] / (r["total_ms"] / 1000.0), 2))
        if r["parsed"]:
            parsed_ok += 1
        pred, hits, ok = _score(r["parsed"], it["expected"])
        for k in field_hits:
            field_hits[k] += int(hits.get(k, False))
        exact += int(ok)
        rows.append({"id": it["id"], "text": it["text"], "expected": it["expected"],
                     "pred": pred, "hits": hits, "exact": ok,
                     "first_ms": r["first_ms"], "total_ms": r["total_ms"],
                     "parse_error": r["parse_error"]})
    n = len(items)
    return {
        "n": n,
        "json_parse_rate": round(parsed_ok / n, 4) if n else None,
        "accuracy": {k: round(v / n, 4) if n else None for k, v in field_hits.items()},
        "exact_match": round(exact / n, 4) if n else None,
        "latency_ms": {"first_token_p50": _pct(firsts, 50), "first_token_p99": _pct(firsts, 99),
                       "total_p50": _pct(totals, 50), "total_p99": _pct(totals, 99),
                       "first_token_mean": round(statistics.mean(firsts), 2) if firsts else None},
        "tokens_per_s_mean": round(statistics.mean(tps), 2) if tps else None,
        "rows": rows,
    }


def _load_jsonl(path):
    from dataio import load_records

    return load_records(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api-base", default="http://127.0.0.1:8080/v1")
    ap.add_argument("--model", default="qwen2-vl-2b-pruned-int8-router")
    ap.add_argument("--base-api-base", default="", help="未量化基线服务，用于计算精度损失")
    ap.add_argument("--base-model", default="qwen2-vl-2b-pruned-fp32-router")
    ap.add_argument("--golden", default=str(DATA / "router_golden.jsonl"))
    ap.add_argument("--golden-mm", default=str(DATA / "router_golden_mm.jsonl"))
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--max-tokens", type=int, default=200)
    ap.add_argument("--out", default=str(ROOT / "eval_report.json"))
    args = ap.parse_args()

    system = _system_prompt()
    text_items = _load_jsonl(args.golden)
    mm_items = _load_jsonl(args.golden_mm) if Path(args.golden_mm).exists() else []
    if args.limit:
        text_items = text_items[:args.limit]
        mm_items = mm_items[:args.limit]

    prune = json.loads((ROOT / "prune_report.json").read_text(encoding="utf-8")) if (ROOT / "prune_report.json").exists() else {}
    quant = json.loads((ROOT / "quantize_report.json").read_text(encoding="utf-8")) if (ROOT / "quantize_report.json").exists() else {}
    int8_bin = ROOT / "models" / "router-pruned-int8" / "pytorch_model.int8.bin"
    size = {
        "prune": prune, "quantize": quant,
        "int8_bin_bytes": int8_bin.stat().st_size if int8_bin.exists() else None,
        "language_compression_vs_fp32": quant.get("compression_vs_fp32"),
        "layer_prune_ratio": prune.get("layer_prune_ratio"),
        "param_prune_ratio": prune.get("param_prune_ratio"),
    }

    print(f"eval text={len(text_items)} mm={len(mm_items)} against {args.api_base}", flush=True)
    text_res = _eval_set(args.api_base, args.model, system, text_items, args.max_tokens)
    mm_res = _eval_set(args.api_base, args.model, system, mm_items, args.max_tokens) if mm_items else None

    report = {"model": args.model, "api_base": args.api_base, "size": size,
              "text": text_res, "multimodal": mm_res}

    if args.base_api_base:
        base_text = _eval_set(args.base_api_base, args.base_model, system, text_items, args.max_tokens)
        delta = {}
        for k in ("turn_scene", "intent", "module"):
            a = (text_res["accuracy"] or {}).get(k)
            b = (base_text["accuracy"] or {}).get(k)
            delta[k] = round(b - a, 4) if a is not None and b is not None else None
        report["baseline"] = {"api_base": args.base_api_base, "text_accuracy": base_text["accuracy"],
                              "accuracy_drop_vs_base": delta,
                              "exact_match_drop": round((base_text["exact_match"] or 0) - (text_res["exact_match"] or 0), 4)}

    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {k: report[k] for k in ("size",)}
    summary["text_accuracy"] = text_res["accuracy"]
    summary["text_exact_match"] = text_res["exact_match"]
    summary["text_latency"] = text_res["latency_ms"]
    if mm_res:
        summary["mm_accuracy"] = mm_res["accuracy"]
        summary["mm_exact_match"] = mm_res["exact_match"]
    if "baseline" in report:
        summary["accuracy_drop_vs_base"] = report["baseline"]["accuracy_drop_vs_base"]
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    print("EVAL_OK", flush=True)


if __name__ == "__main__":
    main()