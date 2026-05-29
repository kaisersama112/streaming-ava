"""多轮消息与最小上下文构造器。"""

from __future__ import annotations

from typing import Any

from ava.multi_turn_context_builder.input import TurnInputAssembler
from ava.multi_turn_context_builder.types import (
    ContextSession,
    ContextTurn,
    ConversationBuildOptions,
    ConversationContext,
)
from ava.domain.conversation.state import ConversationState
from ava.domain.conversation.strategy import BranchStrategy
from ava.domain.multimodal import MediaArtifact, TurnInput


class ConversationMessagesBuilder:
    """统一负责多轮消息数组与最小上下文本体构造。"""

    def __init__(self, turn_input_assembler: TurnInputAssembler | None = None) -> None:
        self.turn_input_assembler = turn_input_assembler or TurnInputAssembler()

    @staticmethod
    def _text_block(text: str, *, output: bool = False) -> dict[str, str] | None:
        cleaned = str(text or "").strip()
        if not cleaned:
            return None
        return {
            "type": "output_text" if output else "input_text",
            "text": cleaned,
        }

    @staticmethod
    def _artifact_label_blocks(raw_artifacts: list[dict[str, object]]) -> list[dict[str, str]]:
        blocks: list[dict[str, str]] = []
        for artifact in raw_artifacts:
            kind = str(artifact.get("kind", "file") or "file").strip()
            name = str(artifact.get("name", "") or "").strip()
            summary = str(artifact.get("summary", "") or "").strip()
            label = f"[{kind}] {name}".strip()
            if summary and summary != name:
                label = f"{label}: {summary}" if label else summary
            if not label:
                continue
            blocks.append({"type": "input_text", "text": label})
        return blocks

    def _artifact_message_blocks(self, artifacts: tuple[MediaArtifact, ...]) -> list[dict[str, Any]]:
        blocks: list[dict[str, Any]] = []
        for artifact in artifacts:
            block = artifact.to_message_block()
            if block is None:
                label_block = self._text_block(artifact.display_label())
                if label_block is not None:
                    blocks.append(label_block)
                continue
            normalized_type = str(block.get("type", "") or "").strip()
            if normalized_type == "text":
                text_block = self._text_block(str(block.get("text", "") or ""))
                if text_block is not None:
                    blocks.append(text_block)
                continue
            if normalized_type == "image_url":
                image_payload = block.get("image_url")
                if isinstance(image_payload, dict):
                    image_url = str(image_payload.get("url", "") or "").strip()
                else:
                    image_url = str(image_payload or "").strip()
                if image_url:
                    blocks.append({"type": "input_image", "image_url": image_url})
                continue
            blocks.append(block)
        return blocks

    @classmethod
    def _record_to_history_messages(cls, record: dict[str, object]) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []

        user_blocks: list[dict[str, Any]] = []
        user_text_block = cls._text_block(str(record.get("user_text", "") or "").strip())
        if user_text_block is not None:
            user_blocks.append(user_text_block)
        user_blocks.extend(cls._artifact_label_blocks(list(record.get("artifacts") or [])))
        if not user_blocks:
            multimodal_summary = str(record.get("multimodal_summary", "") or "").strip()
            fallback_block = cls._text_block(multimodal_summary)
            if fallback_block is not None:
                user_blocks.append(fallback_block)
        if user_blocks:
            messages.append({"role": "user", "content": user_blocks})

        turn_status = str(record.get("turn_status", "completed") or "completed").strip()
        assistant_text = str(record.get("assistant_text", "") or "").strip() if turn_status == "completed" else ""
        assistant_block = cls._text_block(assistant_text, output=True)
        if assistant_block is not None:
            messages.append({"role": "assistant", "content": [assistant_block]})
        return messages

    @staticmethod
    def _should_include_history_messages(strategy: BranchStrategy) -> bool:
        analysis = dict(getattr(strategy, "analysis", {}) or {})
        context_policy = dict(analysis.get("prompt_context_policy", {}) or {})
        return bool(context_policy.get("include_history_messages", True))

    def _load_history_messages(
        self,
        *,
        state: ConversationState,
        options: ConversationBuildOptions,
    ) -> list[dict[str, Any]]:
        max_messages = max(2, int(options.max_context_messages or (options.history_window * 2)))
        if options.current_turn_id is None:
            turn_records = state.turn_records[-max_messages:]
        else:
            turn_records = [
                item
                for item in state.turn_records
                if item.get("turn_id") != options.current_turn_id
            ][-max_messages:]

        flattened_history: list[dict[str, Any]] = []
        for record in turn_records:
            flattened_history.extend(self._record_to_history_messages(record))
        return flattened_history[-max_messages:]

    def build_conversation_context(
        self,
        *,
        state: ConversationState,
        turn_input: TurnInput | str,
        options: ConversationBuildOptions,
        memory_bridge=None,
        continuity_policy=None,
    ) -> ConversationContext:
        del memory_bridge
        del continuity_policy
        if isinstance(turn_input, str):
            turn_input = self.turn_input_assembler.build(turn_input)

        user_text = turn_input.normalized_text() or turn_input.multimodal_summary()
        current_artifacts = tuple(turn_input.artifacts or ())
        conversation = self._load_history_messages(state=state, options=options)

        return ConversationContext(
            session=ContextSession(
                session_id=state.session_id,
                session_scene=state.session_scene,
                turn_scene=state.turn_scene,
                profile=options.profile,
            ),
            current=ContextTurn(
                turn_input=turn_input,
                user_text=user_text,
                artifacts=current_artifacts,
            ),
            conversation=conversation,
        )

    def build_router_messages(
        self,
        *,
        context: ConversationContext,
        text_only: bool = False,
    ) -> list[dict[str, Any]]:
        messages = list(context.conversation)
        user_blocks: list[dict[str, Any]] = []
        text_block = self._text_block(context.current.user_text or "无")
        if text_block is not None:
            user_blocks.append(text_block)
        if not text_only:
            user_blocks.extend(self._artifact_message_blocks(context.current.artifacts))
        messages.append({"role": "user", "content": user_blocks})
        return messages

    def build_responder_messages(
        self,
        *,
        context: ConversationContext,
        strategy: BranchStrategy,
    ) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        if self._should_include_history_messages(strategy):
            messages.extend(context.conversation)

        user_blocks: list[dict[str, Any]] = []
        text_block = self._text_block(context.current.turn_input.normalized_text() or context.current.user_text)
        if text_block is not None:
            user_blocks.append(text_block)
        user_blocks.extend(self._artifact_message_blocks(context.current.artifacts))
        if not user_blocks:
            fallback_block = self._text_block(context.current.user_text)
            if fallback_block is not None:
                user_blocks.append(fallback_block)
        messages.append({"role": "user", "content": user_blocks})
        return messages
