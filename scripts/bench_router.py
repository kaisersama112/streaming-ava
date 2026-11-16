"""路由链路延迟基准：首 token / 端到端 P50/P95/P99，支持并发压测。

用法：
    python scripts/bench_router.py --api-base http://127.0.0.1:8080/v1 --model qwen3-4b-router \
        [--requests 60] [--concurrency 4] [--stream]

对 OpenAI 兼容端点发送真实路由请求（ChatCompletions），--stream 时测量首 token 延迟。
产出 state/bench_router_report.json；P99 目标 ≤1500ms、端侧首 token 目标 ≤700ms。
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("NO_PROXY", "localhost,127.0.0.1")

from openai import OpenAI

ROUTER_SYSTEM = (
    "你是路由分类器。只输出一个 JSON 对象，字段：session_scene, turn_scene, intent, "
    "confidence, need_clarification, should_preserve_teaching_state, plan{module, subject}。"
)
SAMPLES = [
    "解一下这道方程：2x+3=11",
    "我做的对吗？x=4",
    "讲讲什么是一元二次方程",
    "我掌握得怎么样？",
    "今天天气怎么样",
    "你好呀",
    "嗯",
    "帮我算一下 37 乘 24",
]


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round(p / 100 * (len(ordered) - 1)))))
    return round(ordered[idx], 2)


def one_request(client: OpenAI, model: str, text: str, *, stream: bool) -> dict:
    messages = [
        {"role": "system", "content": ROUTER_SYSTEM},
        {"role": "user", "content": text + "\n/no_think"},
    ]
    started = time.monotonic()
    first_token_ms = None
    if stream:
        response = client.chat.completions.create(
            model=model, messages=messages, temperature=0.1, max_tokens=256, stream=True
        )
        for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                first_token_ms = (time.monotonic() - started) * 1000
                break
        for _ in response:
            pass
    else:
        client.chat.completions.create(model=model, messages=messages, temperature=0.1, max_tokens=256)
    total_ms = (time.monotonic() - started) * 1000
    return {"total_ms": total_ms, "first_token_ms": first_token_ms}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base", required=True)
    parser.add_argument("--api-key", default="EMPTY")
    parser.add_argument("--model", required=True)
    parser.add_argument("--requests", type=int, default=60)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--stream", action="store_true")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--out", default="state/bench_router_report.json")
    args = parser.parse_args()

    client = OpenAI(base_url=args.api_base, api_key=args.api_key or "EMPTY", timeout=args.timeout)
    results: list[dict] = []
    failures = 0

    def task(i: int) -> dict | None:
        try:
            return one_request(client, args.model, SAMPLES[i % len(SAMPLES)], stream=args.stream)
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        for result in pool.map(task, range(args.requests)):
            if result is None:
                failures += 1
            else:
                results.append(result)

    totals = [r["total_ms"] for r in results]
    first_tokens = [r["first_token_ms"] for r in results if r["first_token_ms"] is not None]
    report = {
        "requests": args.requests,
        "ok": len(results),
        "failed": failures,
        "concurrency": args.concurrency,
        "stream": args.stream,
        "total_ms": {
            "p50": _percentile(totals, 50),
            "p95": _percentile(totals, 95),
            "p99": _percentile(totals, 99),
            "mean": round(statistics.mean(totals), 2) if totals else 0.0,
        },
        "first_token_ms": {
            "p50": _percentile(first_tokens, 50),
            "p95": _percentile(first_tokens, 95),
            "p99": _percentile(first_tokens, 99),
        } if first_tokens else None,
        "targets": {"p99_total_ms": 1500, "first_token_ms": 700},
        "p99_target_met": _percentile(totals, 99) <= 1500 if totals else False,
        "first_token_target_met": _percentile(first_tokens, 99) <= 700 if first_tokens else None,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()