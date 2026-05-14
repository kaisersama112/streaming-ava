"""Response generation entrypoints.

Generation is split into two phases:

1. `build_turn_plan` converts router output into a locked `TurnPlan`.
2. reply helpers execute that plan through either direct LLM calls or the
   optional Agents SDK backend.

The plan is the stable contract between routing, prompt construction, memory
projection, and realtime TTS submission.
"""

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
