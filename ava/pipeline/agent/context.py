"""Agents SDK 运行时共享上下文。"""

from __future__ import annotations

from dataclasses import dataclass, field
import threading
from typing import Any

from ava.multi_turn_context_builder.types import ConversationContext
from ava.router_selector.schema import RouteDecision
from ava.domain.conversation.state import ConversationState
from ava.domain.conversation.strategy import BranchStrategy


@dataclass
class AvaAgentContext:
    """Agents SDK 本地运行时上下文。

    该对象只供：
    - 动态 instructions
    - tools
    - 回调

    使用。

    注意：
    - 它不会自动暴露给模型
    - 模型真正可见的信息必须通过 instructions 或 tool 输出显式提供
    """

    session_id: str
    turn_id: int | None
    state: ConversationState
    context: ConversationContext
    decision: RouteDecision
    strategy: BranchStrategy
    user_message: dict[str, Any]
    stop_event: threading.Event | None = None
    pending_state_patches: list[dict[str, Any]] = field(default_factory=list)
    debug_events: list[dict[str, Any]] = field(default_factory=list)

    def add_patch(self, *, key: str, value: Any, reason: str) -> None:
        self.pending_state_patches.append(
            {
                "key": str(key or "").strip(),
                "value": value,
                "reason": str(reason or "").strip(),
            }
        )

    def add_event(self, name: str, payload: dict[str, Any] | None = None) -> None:
        self.debug_events.append(
            {
                "name": str(name or "").strip(),
                "payload": dict(payload or {}),
            }
        )
