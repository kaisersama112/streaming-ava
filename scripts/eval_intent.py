"""路由质量评测：黄金集准确率 / F1 / 延迟分位，支持与云侧基线对比精度损失。

用法（端侧小模型）：
    python scripts/eval_intent.py --api-base http://127.0.0.1:8080/v1 --model qwen3-4b-router

与云侧基线对比（精度损失目标 <5%）：
    python scripts/eval_intent.py --api-base http://127.0.0.1:8080/v1 --model qwen3-4b-router \
        --baseline-api-base https://api.example.com/v1 --baseline-model cloud-large --baseline-key-env OPENAI_API_KEY

产出 state/eval_intent_report.json。走真实 RouterService 链路（含治理与解析）。
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import tempfile
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("NO_PROXY", "localhost,127.0.0.1")

from ava.capabilities.prompt.factories import build_prompt_center
from ava.domain.conversation.state import ConversationState
from ava.router_selector.service import RouterService


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round(p / 100 * (len(ordered) - 1)))))
    return round(ordered[idx], 2)


def _macro_f1(pairs: list[tuple[str, str]]) -> float:
    labels = sorted({label for pair in pairs for label in pair})
    f1s = []
    for label in labels:
        tp = sum(1 for expected, predicted in pairs if expected == label and predicted == label)
        fp = sum(1 for expected, predicted in pairs if expected != label and predicted == label)
        fn = sum(1 for expected, predicted in pairs if expected == label and predicted != label)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1s.append(2 * precision * recall / (precision + recall) if precision + recall else 0.0)
    return round(statistics.mean(f1s), 4) if f1s else 0.0


def run_eval(golden: list[dict], *, api_base: str, api_key: str, model: str) -> dict:
    prompt_center = build_prompt_center()
    service = RouterService(prompt_center=prompt_center)
    scene_pairs: list[tuple[str, str]] = []
    intent_correct = 0
    module_correct = 0
    latencies: list[float] = []
    errors: list[dict] = []
    with tempfile.TemporaryDirectory() as tmp:
        for case in golden:
            state = ConversationState(Path(tmp) / f"{case['id']}.json", session_id=case["id"])
            content: list[dict] = [{"type": "input_text", "text": case["text"]}]
            if case.get("has_artifact"):
                content.append({"type": "input_image", "image_url": "data:image/png;base64,iVBORw0KGgo=", "detail": "auto"})
            started = time.monotonic()
            try:
                result = service.route(
                    user_message={"role": "user", "content": content},
                    state=state,
                    history_window=2,
                    model=model,
                    api_base=api_base,
                    api_key=api_key,
                )
            except Exception as exc:
                errors.append({"id": case["id"], "error": str(exc)[:200]})
                continue
            latencies.append((time.monotonic() - started) * 1000)
            expected = case["expected"]
            predicted_scene = result.decision.turn_scene
            scene_pairs.append((expected["turn_scene"], predicted_scene))
            intent_correct += int(result.decision.intent == expected["intent"])
            module_correct += int(str(result.router_plan.get("module", "")) == expected["module"])
    total = len(scene_pairs)
    return {
        "evaluated": total,
        "failed": len(errors),
        "scene_accuracy": round(sum(1 for e, p in scene_pairs if e == p) / total, 4) if total else 0.0,
        "scene_macro_f1": _macro_f1(scene_pairs),
        "intent_accuracy": round(intent_correct / total, 4) if total else 0.0,
        "module_accuracy": round(module_correct / total, 4) if total else 0.0,
        "latency_ms": {
            "p50": _percentile(latencies, 50),
            "p95": _percentile(latencies, 95),
            "p99": _percentile(latencies, 99),
            "mean": round(statistics.mean(latencies), 2) if latencies else 0.0,
        },
        "errors": errors[:10],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--golden", default="data/router_golden.jsonl")
    parser.add_argument("--api-base", required=True)
    parser.add_argument("--api-key", default="")
    parser.add_argument("--model", required=True)
    parser.add_argument("--baseline-api-base", default="")
    parser.add_argument("--baseline-model", default="")
    parser.add_argument("--baseline-key-env", default="OPENAI_API_KEY")
    parser.add_argument("--out", default="state/eval_intent_report.json")
    args = parser.parse_args()

    golden = [json.loads(line) for line in Path(args.golden).read_text(encoding="utf-8").splitlines() if line.strip()]
    report = {"edge": run_eval(golden, api_base=args.api_base, api_key=args.api_key, model=args.model)}
    if args.baseline_api_base and args.baseline_model:
        baseline_key = os.environ.get(args.baseline_key_env, "")
        report["cloud_baseline"] = run_eval(
            golden, api_base=args.baseline_api_base, api_key=baseline_key, model=args.baseline_model
        )
        loss = report["cloud_baseline"]["scene_accuracy"] - report["edge"]["scene_accuracy"]
        report["accuracy_loss"] = round(loss, 4)
        report["accuracy_loss_target_met"] = loss < 0.05
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()