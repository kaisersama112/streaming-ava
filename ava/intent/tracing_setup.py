"""关闭 Agents SDK 自带 trace 导出。

SDK 默认 provider 会构造 trust_env 的 httpx 客户端向 OpenAI 平台上报 trace，
Windows 注册表中的非法代理值会让该客户端在构造期崩溃（Invalid port），
且 RunConfig.tracing_disabled 无法阻止 provider 初始化。这里安装无导出 provider，
全链路观测由项目自有 ava.core.tracing 承担。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from agents.tracing import set_trace_provider
from agents.tracing.processor_interface import TracingProcessor
from agents.tracing.provider import TraceProvider
from agents.tracing.scope import Scope
from agents.tracing.spans import NoOpSpan, Span, TSpanData
from agents.tracing.traces import NoOpTrace, Trace


class _NoExportTraceProvider(TraceProvider):
    def register_processor(self, processor: TracingProcessor) -> None:
        return None

    def set_processors(self, processors: list[TracingProcessor]) -> None:
        return None

    def get_current_trace(self) -> Trace | None:
        return Scope.get_current_trace()

    def get_current_span(self) -> Span[Any] | None:
        return Scope.get_current_span()

    def set_disabled(self, disabled: bool) -> None:
        return None

    def time_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def gen_trace_id(self) -> str:
        return f"trace_{uuid.uuid4().hex}"

    def gen_span_id(self) -> str:
        return f"span_{uuid.uuid4().hex[:16]}"

    def gen_group_id(self) -> str:
        return f"group_{uuid.uuid4().hex}"

    def create_trace(
        self,
        name: str,
        trace_id: str | None = None,
        group_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        disabled: bool = False,
        tracing: Any = None,
    ) -> Trace:
        return NoOpTrace()

    def create_span(
        self,
        span_data: TSpanData,
        span_id: str | None = None,
        parent: Trace | Span[Any] | None = None,
        disabled: bool = False,
    ) -> Span[TSpanData]:
        return NoOpSpan(span_data)


set_trace_provider(_NoExportTraceProvider())