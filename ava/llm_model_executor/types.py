"""模型执行器核心类型。"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol


class InferenceTask(str, Enum):
    ROUTE = "route"
    GENERATE = "generate"


@dataclass(frozen=True)
class ModelRequestContext:
    """传给模型执行器的纯请求上下文。"""

    task: InferenceTask
    session_id: str
    model: str
    instructions: str
    input: list[dict[str, object]]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class InferenceRequest:
    """传给底层 provider 的标准请求。"""

    task: InferenceTask
    model: str
    payload: dict[str, Any]
    stream: bool = False
    timeout: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class InferenceResult:
    """模型执行结果。"""

    text: str
    raw: Any | None = None
    usage: Any | None = None
    finish_reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class InferenceEvent:
    """流式事件基类。"""


@dataclass(frozen=True)
class OutputTextDelta(InferenceEvent):
    text: str


@dataclass(frozen=True)
class InferenceCompleted(InferenceEvent):
    text: str
    finish_reason: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class InferenceError(InferenceEvent):
    error: str


class LLMProvider(Protocol):
    """底层模型 provider 协议。"""

    def chat(self, request: InferenceRequest) -> InferenceResult:
        ...

    def stream(
        self,
        request: InferenceRequest,
        *,
        stop_event: threading.Event | None = None,
    ):
        ...
