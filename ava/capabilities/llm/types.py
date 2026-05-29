"""旧 LLM 类型入口，转发到 `ava.llm_model_executor.types`。"""

from ava.llm_model_executor.types import (
    InferenceCompleted,
    InferenceError,
    InferenceEvent,
    InferenceRequest,
    InferenceResult,
    InferenceTask,
    LLMProvider,
    ModelRequestContext,
    OutputTextDelta,
)

__all__ = [
    "InferenceCompleted",
    "InferenceError",
    "InferenceEvent",
    "InferenceRequest",
    "InferenceResult",
    "InferenceTask",
    "LLMProvider",
    "ModelRequestContext",
    "OutputTextDelta",
]
