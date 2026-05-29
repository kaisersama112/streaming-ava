"""Router 专用的消息与指令组装器。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ava.capabilities.prompt.prompt_builder import PromptCenter
from ava.multi_turn_context_builder.types import ConversationBuildOptions, ConversationContext
from ava.domain.conversation.state import ConversationState
from ava.domain.multimodal import TurnInput

if False:
    from ava.multi_turn_context_builder.compiler import ContextCompiler


@dataclass(frozen=True)
class RouterRequestArtifacts:
    """Router 阶段的请求装配结果。"""

    context: ConversationContext
    instructions: str
    input: list[dict[str, object]]
    active_skills: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class RouterRequestBuilder:
    """构建 router 阶段的 `instructions + input`。"""

    def __init__(self, compiler: "ContextCompiler") -> None:
        self.compiler = compiler

    def build(
        self,
        *,
        prompt_center: PromptCenter,
        state: ConversationState,
        turn_input: TurnInput | str,
        options: ConversationBuildOptions,
        context: ConversationContext | None = None,
        text_only: bool = False,
    ) -> RouterRequestArtifacts:
        current_context = context or self.compiler.build_conversation_context(
            state=state,
            turn_input=turn_input,
            options=options,
        )
        compiled_payload = self.compiler.compile_router_payload(
            prompt_center=prompt_center,
            context=current_context,
            text_only=text_only,
        )
        return RouterRequestArtifacts(
            context=current_context,
            instructions=compiled_payload.instructions,
            input=list(compiled_payload.input),
            active_skills=list(compiled_payload.active_skills),
            metadata={
                "text_only": text_only,
                "context_profile": current_context.session.profile,
                "instruction_sections": compiled_payload.sections,
            },
        )
