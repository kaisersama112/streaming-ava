"""Structured append-only trace logging for step-by-step debugging."""

from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from config import BASE_DIR, settings

_TRACE_LOCK = threading.Lock()


def _resolve_path(path_str: str) -> Path:
    path = Path(path_str)
    if path.is_absolute():
        return path
    return BASE_DIR / path


def _truncate_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    remaining = len(text) - limit
    return f"{text[:limit]}...<truncated {remaining} chars>"


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()[:16]


def sanitize_value(value: Any, *, text_limit: int | None = None) -> Any:
    limit = int(text_limit or getattr(settings.runtime, "trace_max_text_chars", 12000) or 12000)

    if value is None or isinstance(value, (bool, int, float)):
        return value

    if isinstance(value, bytes):
        return {
            "type": "bytes",
            "length": len(value),
            "sha256": hashlib.sha256(value).hexdigest()[:16],
        }

    if isinstance(value, str):
        if value.startswith("data:"):
            return {
                "type": "data_url",
                "length": len(value),
                "sha256": _hash_text(value),
                "prefix": value[:64],
            }
        return _truncate_text(value, limit)

    if isinstance(value, dict):
        return {str(key): sanitize_value(item, text_limit=limit) for key, item in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [sanitize_value(item, text_limit=limit) for item in value]

    if hasattr(value, "model_dump"):
        try:
            return sanitize_value(value.model_dump(), text_limit=limit)
        except Exception:
            pass

    if hasattr(value, "to_metadata"):
        try:
            return sanitize_value(value.to_metadata(), text_limit=limit)
        except Exception:
            pass

    if hasattr(value, "__dict__"):
        try:
            return sanitize_value(dict(value.__dict__), text_limit=limit)
        except Exception:
            pass

    return _truncate_text(str(value), limit)


def sanitize_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sanitize_value(messages)


def sanitize_turn_input(turn_input: Any) -> dict[str, Any]:
    if turn_input is None:
        return {}
    artifacts = []
    for artifact in getattr(turn_input, "artifacts", ()) or ():
        metadata = dict(getattr(artifact, "metadata", {}) or {})
        entry = {
            "kind": getattr(artifact, "kind", ""),
            "name": getattr(artifact, "name", ""),
            "mime_type": getattr(artifact, "mime_type", ""),
            "summary": getattr(artifact, "summary", ""),
            "uri": getattr(artifact, "uri", None),
            "has_data_url": bool(getattr(artifact, "data_url", None)),
            "data_url_hash": _hash_text(getattr(artifact, "data_url", "")) if getattr(artifact, "data_url", None) else "",
            "metadata": sanitize_value(metadata),
        }
        artifacts.append(entry)
    return {
        "text": getattr(turn_input, "normalized_text", lambda: str(getattr(turn_input, "text", "")))(),
        "memory_text": getattr(turn_input, "memory_text", lambda: "")(),
        "multimodal_summary": getattr(turn_input, "multimodal_summary", lambda: "")(),
        "source": getattr(turn_input, "source", ""),
        "artifacts": artifacts,
    }


def sanitize_context_snapshot(snapshot: Any) -> dict[str, Any]:
    if snapshot is None:
        return {}
    return {
        "user_text": getattr(snapshot, "user_text", ""),
        "session_id": getattr(snapshot, "session_id", ""),
        "session_scene": getattr(snapshot, "session_scene", ""),
        "turn_scene": getattr(snapshot, "turn_scene", ""),
        "recent_history_summary": getattr(snapshot, "recent_history_summary", ""),
        "multimodal_summary": getattr(snapshot, "multimodal_summary", ""),
        "recent_turns_summary": getattr(snapshot, "recent_turns_summary", ""),
        "education_state": sanitize_value(getattr(snapshot, "education_state", {})),
        "facts": sanitize_value(getattr(snapshot, "facts", {})),
        "history_messages": sanitize_messages(getattr(snapshot, "history_messages", []) or []),
        "artifacts": sanitize_value([artifact.to_prompt_dict() for artifact in (getattr(snapshot, "artifacts", ()) or ())]),
        "reference_artifacts": sanitize_value(
            [artifact.to_prompt_dict() for artifact in (getattr(snapshot, "reference_artifacts", ()) or ())]
        ),
        "router_artifact_brief": sanitize_value(getattr(snapshot, "router_artifact_brief", {}) or {}),
    }


def append_trace_log(
    step: str,
    payload: dict[str, Any],
    *,
    turn_id: int | None = None,
    trace_id: str | None = None,
    scope: str = "",
) -> None:
    if not bool(getattr(settings.runtime, "trace_log_enabled", True)):
        return
    path = _resolve_path(getattr(settings.runtime, "trace_log_file", "state/trace.jsonl"))
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "logged_at": datetime.now().isoformat(timespec="seconds"),
        "step": step,
        "turn_id": turn_id,
        "trace_id": trace_id or "",
        "scope": scope,
        "payload": sanitize_value(payload),
    }
    with _TRACE_LOCK:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")


__all__ = [
    "append_trace_log",
    "sanitize_context_snapshot",
    "sanitize_messages",
    "sanitize_turn_input",
    "sanitize_value",
]
