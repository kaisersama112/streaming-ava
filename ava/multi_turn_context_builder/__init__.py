"""多轮上下文构造器。"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .compiler import ContextCompiler, ContextContinuityPolicy
    from .input import AttachmentPayload, TurnInputAssembler
    from .messages import ConversationMessagesBuilder
    from .types import (
        CompiledConversationPayload,
        CompiledInstructions,
        ConversationBuildOptions,
        ConversationContext,
        SkillSelection,
    )

__all__ = [
    "AttachmentPayload",
    "CompiledConversationPayload",
    "CompiledInstructions",
    "ContextCompiler",
    "ContextContinuityPolicy",
    "ConversationBuildOptions",
    "ConversationContext",
    "ConversationMessagesBuilder",
    "SkillSelection",
    "TurnInputAssembler",
]


def __getattr__(name: str):
    if name in {"ContextCompiler", "ContextContinuityPolicy"}:
        from .compiler import ContextCompiler, ContextContinuityPolicy

        mapping = {
            "ContextCompiler": ContextCompiler,
            "ContextContinuityPolicy": ContextContinuityPolicy,
        }
        return mapping[name]
    if name in {"AttachmentPayload", "TurnInputAssembler"}:
        from .input import AttachmentPayload, TurnInputAssembler

        mapping = {
            "AttachmentPayload": AttachmentPayload,
            "TurnInputAssembler": TurnInputAssembler,
        }
        return mapping[name]
    if name == "ConversationMessagesBuilder":
        from .messages import ConversationMessagesBuilder

        return ConversationMessagesBuilder
    if name in {"CompiledConversationPayload", "CompiledInstructions", "ConversationBuildOptions", "ConversationContext", "SkillSelection"}:
        from .types import (
            CompiledConversationPayload,
            CompiledInstructions,
            ConversationBuildOptions,
            ConversationContext,
            SkillSelection,
        )

        mapping = {
            "CompiledConversationPayload": CompiledConversationPayload,
            "CompiledInstructions": CompiledInstructions,
            "ConversationBuildOptions": ConversationBuildOptions,
            "ConversationContext": ConversationContext,
            "SkillSelection": SkillSelection,
        }
        return mapping[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
