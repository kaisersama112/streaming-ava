from typing import Protocol
import threading

from ava.capabilities.llm.streaming.events import InferenceEvent
from ava.capabilities.llm.types import InferenceRequest, InferenceResult


class LLMProvider(Protocol):
    def chat(self, request: InferenceRequest) -> InferenceResult:
        ...

    def stream(
        self,
        request: InferenceRequest,
        *,
        stop_event: threading.Event | None = None,
    ) -> list[InferenceEvent] | tuple[InferenceEvent, ...] | object:
        ...

