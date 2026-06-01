"""Conversation domain models."""

from __future__ import annotations

from ava.multi_turn_context_builder.types import ConversationContext

__all__ = [
    "BranchStrategy",
    "ConversationContext",
    "ConversationState",
    "EducationTurnFrame",
    "PromptSelection",
    "PromptSelectionTrace",
    "ResolvedPromptSpec",
    "ScenarioPolicy",
    "SelectionTraceStep",
]


def __getattr__(name: str):
    if name == "ConversationState":
        from ava.domain.conversation.state import ConversationState

        return ConversationState
    if name in {
        "BranchStrategy",
        "EducationTurnFrame",
        "PromptSelection",
        "PromptSelectionTrace",
        "ResolvedPromptSpec",
        "ScenarioPolicy",
        "SelectionTraceStep",
    }:
        from ava.domain.conversation import strategy as strategy_module

        return getattr(strategy_module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
