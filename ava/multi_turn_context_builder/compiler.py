"""统一上下文编译入口。"""

from __future__ import annotations

from ava.multi_turn_context_builder.input import AttachmentPayload, TurnInputAssembler
from ava.multi_turn_context_builder.instructions import InstructionsCompiler
from ava.multi_turn_context_builder.messages import ConversationMessagesBuilder
from ava.multi_turn_context_builder.types import (
    CompiledConversationPayload,
    ConversationBuildOptions,
    ConversationContext,
)
from ava.domain.conversation.state import ConversationState
from ava.domain.conversation.strategy import BranchStrategy
from ava.domain.multimodal import MediaArtifact, TurnInput


class ContextContinuityPolicy:
    """上下文连续性策略。"""

    @staticmethod
    def build_artifact_brief_for_turn(
        state: ConversationState,
        *,
        current_artifacts: tuple[MediaArtifact, ...] = (),
    ) -> dict[str, object]:
        if not current_artifacts:
            return {}
        return state.memory.cached_or_metadata_artifact_analysis(current_artifacts)

    @staticmethod
    def should_isolate_current_artifact_context(
        state: ConversationState,
        context: ConversationContext,
        *,
        current_turn_id: int | None = None,
    ) -> bool:
        current_artifacts = tuple(context.current.artifacts or ())
        if not current_artifacts:
            return False

        previous_artifacts = state.recent_reference_artifacts(
            current_turn_id=current_turn_id,
            limit_turns=1,
        )
        if not previous_artifacts:
            return True

        current_key = state.memory.artifact_bundle_key(current_artifacts)
        previous_key = state.memory.artifact_bundle_key(previous_artifacts)
        if current_key and current_key == previous_key:
            return False
        return True

    @staticmethod
    def select_router_model(
        *,
        current_artifacts: tuple[MediaArtifact, ...],
        text_only: bool,
        model: str,
        multimodal_model: str,
    ) -> str:
        if text_only:
            return model
        if current_artifacts:
            return multimodal_model
        return model


class ContextCompiler:
    """统一上下文编译入口。"""

    def __init__(
        self,
        *,
        continuity_policy: ContextContinuityPolicy | None = None,
        messages_builder: ConversationMessagesBuilder | None = None,
        instructions_compiler: InstructionsCompiler | None = None,
        turn_input_assembler: TurnInputAssembler | None = None,
    ) -> None:
        self.continuity_policy = continuity_policy or ContextContinuityPolicy()
        self.turn_input_assembler = turn_input_assembler or TurnInputAssembler()
        self.messages_builder = messages_builder or ConversationMessagesBuilder(
            turn_input_assembler=self.turn_input_assembler,
        )
        self.instructions_compiler = instructions_compiler or InstructionsCompiler()

    def build_turn_input(
        self,
        text: str | None = None,
        attachments: list[AttachmentPayload] | None = None,
        source: str = "web",
    ) -> TurnInput:
        return self.turn_input_assembler.build(text=text, attachments=attachments, source=source)

    def build_conversation_context(
        self,
        *,
        state: ConversationState,
        turn_input: TurnInput | str,
        options: ConversationBuildOptions,
    ) -> ConversationContext:
        return self.messages_builder.build_conversation_context(
            state=state,
            turn_input=turn_input,
            options=options,
        )

    def build_router_messages(
        self,
        *,
        context: ConversationContext,
        text_only: bool = False,
    ) -> list[dict[str, object]]:
        return self.messages_builder.build_router_messages(context=context, text_only=text_only)

    def build_responder_messages(
        self,
        *,
        context: ConversationContext,
        strategy: BranchStrategy,
    ) -> list[dict[str, object]]:
        return self.messages_builder.build_responder_messages(context=context, strategy=strategy)

    def compile_router_payload(
        self,
        *,
        prompt_center,
        context: ConversationContext,
        text_only: bool = False,
    ) -> CompiledConversationPayload:
        compiled_instructions = self.instructions_compiler.compile_router(
            prompt_center=prompt_center,
            context=context,
        )
        messages = self.build_router_messages(
            context=context,
            text_only=text_only,
        )
        return CompiledConversationPayload(
            instructions=compiled_instructions.text,
            input=messages,
            context=context,
            active_skills=list(compiled_instructions.active_skills),
            sections=dict(compiled_instructions.sections or {}),
        )

    def compile_responder_payload(
        self,
        *,
        prompt_center,
        context: ConversationContext,
        strategy: BranchStrategy,
        decision,
    ) -> CompiledConversationPayload:
        compiled_instructions = self.instructions_compiler.compile_responder(
            prompt_center=prompt_center,
            context=context,
            strategy=strategy,
            decision=decision,
        )
        messages = self.build_responder_messages(
            context=context,
            strategy=strategy,
        )
        return CompiledConversationPayload(
            instructions=compiled_instructions.text,
            input=messages,
            context=context,
            active_skills=list(compiled_instructions.active_skills),
            sections=dict(compiled_instructions.sections or {}),
        )
