"""Pipeline response generation entrypoints."""

from .dispatcher import build_turn_plan
from .types import TurnPlan

__all__ = [
    "TurnPlan",
    "build_turn_plan",
    "ReplyExecutionResult",
    "generate_reply_sync",
    "stream_reply_with_callbacks",
]


def __getattr__(name: str):
    if name in {"ReplyExecutionResult", "generate_reply_sync", "stream_reply_with_callbacks"}:
        from ava.pipeline.generation.reply_service import (
            ReplyExecutionResult,
            generate_reply_sync,
            stream_reply_with_callbacks,
        )
        mapping = {
            "ReplyExecutionResult": ReplyExecutionResult,
            "generate_reply_sync": generate_reply_sync,
            "stream_reply_with_callbacks": stream_reply_with_callbacks,
        }
        return mapping[name]
    raise AttributeError(name)
