from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ava.domain.multimodal import TurnInput


class InferenceTask(str, Enum):
    ROUTE = "route"
    GENERATE = "generate"


@dataclass(frozen=True)
class LLMContext:
    task: InferenceTask
    session_id: str
    current_input: TurnInput
    history: list[dict[str, Any]]
    memory: dict[str, Any] | None = None
    multimodal: dict[str, Any] | None = None
    strategy: dict[str, Any] | None = None
    routing: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class InferenceRequest:
    task: InferenceTask
    model: str
    instructions: str
    input: str | list[dict[str, Any]]
    history: list[dict[str, Any]] = field(default_factory=list)
    response_format: dict[str, Any] | None = None
    tools: list[dict[str, Any]] = field(default_factory=list)
    stream: bool = False
    temperature: float | None = None
    max_tokens: int | None = None
    timeout: float | None = None
    modalities: list[str] = field(default_factory=lambda: ["text"])
    extra_body: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class InferenceResult:
    text: str
    raw: Any | None = None
    usage: Any | None = None
    finish_reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

