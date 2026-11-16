"""统一全链路 trace 埋点。

所有路由决策、模型选择、上下文快照、Agent 事件、状态 patch 与端云降级
都通过这里落盘，schema 统一，便于问题定位与策略迭代。
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from configs import BASE_DIR, settings

_WRITE_LOCK = threading.Lock()

_TOP_LEVEL_KEYS = ("event", "actor", "session_id", "turn_id", "trace_id", "latency_ms")


def new_trace_id() -> str:
    return uuid.uuid4().hex[:16]


def _resolve_path(path_str: str) -> Path:
    path = Path(str(path_str or "").strip() or "state/trace.jsonl")
    if path.is_absolute():
        return path
    return BASE_DIR / path


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "model_dump") and callable(value.model_dump):
        return _json_safe(value.model_dump(mode="json"))
    if hasattr(value, "to_payload") and callable(value.to_payload):
        return _json_safe(value.to_payload())
    return str(value)


def append_trace_log(payload: dict[str, Any], *, log_file: str | None = None) -> dict[str, Any]:
    """追加一条统一 schema 的 trace 记录。

    兼容扁平写法 ``{"event": ..., "key": ...}``：除保留字段外全部归入 payload。
    """
    source = dict(payload or {})
    record: dict[str, Any] = {
        "ts": datetime.now().isoformat(timespec="milliseconds"),
        "event": str(source.get("event") or "unknown").strip(),
        "actor": str(source.get("actor") or "").strip(),
        "session_id": str(source.get("session_id") or "").strip(),
        "turn_id": source.get("turn_id"),
        "trace_id": str(source.get("trace_id") or "").strip() or new_trace_id(),
        "latency_ms": source.get("latency_ms"),
        "payload": _json_safe(source.get("payload") if "payload" in source else {
            key: value for key, value in source.items() if key not in _TOP_LEVEL_KEYS and key != "ts"
        }),
    }
    if not bool(getattr(settings.runtime, "trace_enabled", True)):
        return record
    path = _resolve_path(log_file or str(getattr(settings.runtime, "trace_log_file", "state/trace.jsonl")))
    try:
        with _WRITE_LOCK:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass
    return record


def record_turn_evaluation(
    *,
    session_id: str,
    turn_id: int | None,
    trace_id: str,
    evaluation: dict[str, Any],
    decision: Any = None,
    reply_debug: dict[str, Any] | None = None,
    timeline_ms: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """按 turn 落一条评估记录，供离线分析与策略迭代。"""
    debug = dict(reply_debug or {})
    orchestration = dict(debug.get("orchestration") or {})
    record = {
        "ts": datetime.now().isoformat(timespec="milliseconds"),
        "session_id": str(session_id or ""),
        "turn_id": turn_id,
        "trace_id": str(trace_id or ""),
        "evaluation": _json_safe(dict(evaluation or {})),
        "decision": _json_safe(decision),
        "model_selection": _json_safe(debug.get("model_selection") or {}),
        "orchestration": {
            "mode": orchestration.get("mode"),
            "skills": [
                {"skill": item.get("skill"), "status": item.get("status"), "latency_ms": item.get("latency_ms")}
                for item in orchestration.get("results") or []
                if isinstance(item, dict)
            ],
            "latency_ms": orchestration.get("latency_ms"),
        },
        "patches": {
            "applied": len(debug.get("applied_state_patches") or []),
            "rejected": len(debug.get("rejected_state_patches") or []),
        },
        "timeline_ms": _json_safe(timeline_ms or {}),
    }
    if not bool(getattr(settings.runtime, "trace_enabled", True)):
        return record
    path = _resolve_path(str(getattr(settings.runtime, "evaluation_log_file", "state/evaluation.jsonl")))
    try:
        with _WRITE_LOCK:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass
    return record


def trace_event(
    event: str,
    *,
    actor: str = "",
    session_id: str = "",
    turn_id: int | None = None,
    trace_id: str = "",
    latency_ms: float | None = None,
    log_file: str | None = None,
    **payload: Any,
) -> dict[str, Any]:
    """结构化埋点入口。"""
    return append_trace_log(
        {
            "event": event,
            "actor": actor,
            "session_id": session_id,
            "turn_id": turn_id,
            "trace_id": trace_id,
            "latency_ms": latency_ms,
            "payload": payload,
        },
        log_file=log_file,
    )