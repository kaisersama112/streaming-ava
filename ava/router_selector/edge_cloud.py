"""端云协同路由支撑：路由指纹缓存 + 端侧小模型请求构造。

端侧（llama.cpp / ONNX Runtime / MNN 的 OpenAI 兼容服务）承担高频低延迟路由，
失败 / 超时 / 低置信时由 RouterService 降级云侧，降级原因落 trace。
"""

from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import replace
from typing import Any

from ava.llm_model_executor.types import ModelRequestContext


class RouteCache:
    """线程安全的 TTL 路由结果缓存（只缓存决策，不缓存上下文对象）。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: dict[str, tuple[float, dict[str, Any]]] = {}

    def get(self, key: str, *, ttl_seconds: float) -> dict[str, Any] | None:
        now = time.monotonic()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            stored_at, value = entry
            if now - stored_at > max(0.0, float(ttl_seconds)):
                self._entries.pop(key, None)
                return None
            return dict(value)

    def put(self, key: str, value: dict[str, Any]) -> None:
        with self._lock:
            if len(self._entries) >= 256:
                oldest = min(self._entries, key=lambda k: self._entries[k][0])
                self._entries.pop(oldest, None)
            self._entries[key] = (time.monotonic(), dict(value))

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


def route_fingerprint(*, context_snapshot: str, session_scene: str, model: str) -> str:
    raw = f"{context_snapshot}|{session_scene}|{model}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def build_edge_request_context(
    request_context: ModelRequestContext,
    *,
    api_base: str,
    api_key: str,
    model: str,
    timeout_ms: int,
    no_think: bool,
) -> ModelRequestContext:
    """把云侧路由请求改写为端侧小模型请求。"""
    metadata = dict(request_context.metadata or {})
    metadata["api_base"] = str(api_base or "").strip()
    metadata["api_key"] = str(api_key or "").strip()
    metadata["timeout"] = max(0.05, float(timeout_ms) / 1000.0)
    metadata["provider"] = "edge_local"

    input_items = [dict(item) for item in list(request_context.input or [])]
    if no_think and input_items:
        last = dict(input_items[-1])
        content = last.get("content")
        if isinstance(content, str) and content.strip():
            last["content"] = f"{content.rstrip()}\n/no_think"
        elif isinstance(content, list):
            blocks = [dict(block) for block in content]
            for block in reversed(blocks):
                if str(block.get("type", "") or "") in {"input_text", "text"} and str(block.get("text", "") or "").strip():
                    block["text"] = f"{str(block['text']).rstrip()} /no_think"
                    break
            last["content"] = blocks
        input_items[-1] = last

    return replace(
        request_context,
        model=str(model or "").strip() or request_context.model,
        input=input_items,
        metadata=metadata,
    )