"""Model-visible memory projection builder."""

from __future__ import annotations

from typing import Any

from ava.domain.memory.types import MessageBlockMemoryEntry, MemoryProjection


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return str(value)


def _trim_dict(source: dict[str, Any], *, allowed_keys: tuple[str, ...]) -> dict[str, Any]:
    return {
        key: source.get(key)
        for key in allowed_keys
        if source.get(key) not in (None, "", [], {}, ())
    }


class MemoryProjector:
    def build(
            self,
            memory,
            user_message: dict[str, Any],
            *,
            profile: str,
            current_message_blocks: list[dict[str, Any]] | tuple[dict[str, Any], ...] = (),
            reference_message_blocks: list[dict[str, Any]] | tuple[dict[str, Any], ...] = (),
    ) -> MemoryProjection:
        target = current_message_blocks or reference_message_blocks
        message_block_memory: list[dict[str, Any]] = []
        if target:
            analysis = memory.cached_or_metadata_block_analysis(target)
            if analysis:
                message_block_memory.append(
                    MessageBlockMemoryEntry(
                        block_bundle_key=memory.block_bundle_key(target),
                        analysis=_json_safe(analysis),
                    ).to_payload()
                )

        retrieved_memories = [
            item.to_payload()
            for item in memory.retrieve_relevant_memories(
                user_message,
                current_message_blocks=current_message_blocks,
                reference_message_blocks=reference_message_blocks,
            )
        ]

        projection = MemoryProjection(
            recent_topics=list(memory.recent_topics or []),
            context_summary=str(memory.context_summary or "").strip(),
            multimodal_context_summary=str(memory.multimodal_context_summary or "").strip(),
            education_state=dict(memory.education_state or {}),
            message_block_memory=message_block_memory,
            retrieved_memories=[_json_safe(item) for item in retrieved_memories],
        )
        if profile == "router":
            return MemoryProjection(
                recent_topics=list(projection.recent_topics)[:4],
                education_state=_trim_dict(
                    dict(projection.education_state),
                    allowed_keys=(
                        "subject",
                        "knowledge_point",
                        "stage",
                        "learning_scenario",
                        "learning_objects",
                        "object_scope",
                        "object_continuity",
                        "primary_action",
                        "answer_boundary",
                        "previous_strategy_id",
                        "previous_policy_id",
                    ),
                ),
                message_block_memory=list(projection.message_block_memory)[:1],
                retrieved_memories=list(projection.retrieved_memories)[:3],
            )

        return projection
