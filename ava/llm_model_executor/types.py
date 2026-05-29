"""LLM 能力层共享类型。"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol


class InferenceTask(str, Enum):
    """推理任务类型。"""

    ROUTE = "route"
    GENERATE = "generate"


@dataclass(frozen=True)
class ModelRequestContext:
    """面向模型请求的简化上下文。

    这里不再保存大量中间态对象，而是直接围绕模型真正消费的两类数据组织：
    - instructions
    - messages
    """

    task: InferenceTask
    session_id: str
    model: str
    instructions: str
    messages: list[dict[str, object]]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class InferenceRequest:
    """发送给 provider 的标准请求。"""

    task: InferenceTask
    model: str
    payload: dict[str, Any]
    stream: bool = False
    timeout: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class InferenceResult:
    """模型执行结束后的标准结果。"""

    text: str
    raw: Any | None = None
    usage: Any | None = None
    finish_reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class InferenceEvent:
    """流式推理事件基类。"""

    pass


@dataclass(frozen=True)
class OutputTextDelta(InferenceEvent):
    """流式输出中的文本增量。"""

    text: str


@dataclass(frozen=True)
class InferenceCompleted(InferenceEvent):
    """流式推理完成事件。"""

    text: str
    finish_reason: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class InferenceError(InferenceEvent):
    """流式推理错误事件。"""

    error: str


class LLMProvider(Protocol):
    """底层模型提供方协议。"""

    def chat(self, request: InferenceRequest) -> InferenceResult:
        ...

    def stream(
        self,
        request: InferenceRequest,
        *,
        stop_event: threading.Event | None = None,
    ) -> list[InferenceEvent] | tuple[InferenceEvent, ...] | object:
        ...
