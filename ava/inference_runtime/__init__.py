"""推理运行时。"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .reply_service import ReplyExecutionResult, generate_reply_sync, stream_reply_with_callbacks
    from .turn_planner import build_turn_plan

__all__ = [
    "ReplyExecutionResult",
    "build_turn_plan",
    "generate_reply_sync",
    "stream_reply_with_callbacks",
]


def __getattr__(name: str):
    if name == "build_turn_plan":
        from .turn_planner import build_turn_plan

        return build_turn_plan
    if name in {"ReplyExecutionResult", "generate_reply_sync", "stream_reply_with_callbacks"}:
        from .reply_service import ReplyExecutionResult, generate_reply_sync, stream_reply_with_callbacks

        mapping = {
            "ReplyExecutionResult": ReplyExecutionResult,
            "generate_reply_sync": generate_reply_sync,
            "stream_reply_with_callbacks": stream_reply_with_callbacks,
        }
        return mapping[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
