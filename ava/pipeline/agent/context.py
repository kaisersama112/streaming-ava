"""Shared runtime context passed through OpenAI Agents SDK runs."""

from __future__ import annotations

from dataclasses import dataclass, field
import threading
from typing import Any

from ava.multi_turn_context_builder.types import ConversationContext
from ava.domain.multimodal import TurnInput
from ava.router_selector.schema import RouteDecision
from ava.domain.conversation.state import ConversationState
from ava.domain.conversation.strategy import BranchStrategy


@dataclass
class AvaAgentContext:
    """Local-only execution context for Agents SDK runs.

    This object is available to dynamic instructions, tools, and callbacks.
    It is not automatically exposed to the model; anything the model must know
    needs to be surfaced via instructions or tool outputs.
    """

    session_id: str
    turn_id: int | None
    state: ConversationState
    context: ConversationContext
    decision: RouteDecision
    strategy: BranchStrategy
    turn_input: TurnInput
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
