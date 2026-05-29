"""模型执行器。"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .provider import OpenAIResponsesProvider
    from .request import InferenceRequestBuilder, RequestPolicy
    from .service import LLMService, RequestContextBuilder
    from .types import (
        InferenceCompleted,
        InferenceError,
        InferenceEvent,
        InferenceRequest,
        InferenceResult,
        InferenceTask,
        ModelRequestContext,
        OutputTextDelta,
    )

__all__ = [
    "InferenceCompleted",
    "InferenceError",
    "InferenceEvent",
    "InferenceRequest",
    "InferenceRequestBuilder",
    "InferenceResult",
    "InferenceTask",
    "LLMService",
    "ModelRequestContext",
    "OpenAIResponsesProvider",
    "OutputTextDelta",
    "RequestContextBuilder",
    "RequestPolicy",
]


def __getattr__(name: str):
    if name in {"OpenAIResponsesProvider"}:
        from .provider import OpenAIResponsesProvider

        return OpenAIResponsesProvider
    if name in {"InferenceRequestBuilder", "RequestPolicy"}:
        from .request import InferenceRequestBuilder, RequestPolicy

        mapping = {
            "InferenceRequestBuilder": InferenceRequestBuilder,
            "RequestPolicy": RequestPolicy,
        }
        return mapping[name]
    if name in {"LLMService", "RequestContextBuilder"}:
        from .service import LLMService, RequestContextBuilder

        mapping = {
            "LLMService": LLMService,
            "RequestContextBuilder": RequestContextBuilder,
        }
        return mapping[name]
    if name in {
        "InferenceCompleted",
        "InferenceError",
        "InferenceEvent",
        "InferenceRequest",
        "InferenceResult",
        "InferenceTask",
        "ModelRequestContext",
        "OutputTextDelta",
    }:
        from .types import (
            InferenceCompleted,
            InferenceError,
            InferenceEvent,
            InferenceRequest,
            InferenceResult,
            InferenceTask,
            ModelRequestContext,
            OutputTextDelta,
        )

        mapping = {
            "InferenceCompleted": InferenceCompleted,
            "InferenceError": InferenceError,
            "InferenceEvent": InferenceEvent,
            "InferenceRequest": InferenceRequest,
            "InferenceResult": InferenceResult,
            "InferenceTask": InferenceTask,
            "ModelRequestContext": ModelRequestContext,
            "OutputTextDelta": OutputTextDelta,
        }
        return mapping[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
