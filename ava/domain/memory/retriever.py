"""Relevant memory retrieval for one turn."""

from __future__ import annotations

from typing import Any

from ava.domain.memory.types import MessageBlockMemoryEntry, RetrievedMemory


def _trim_dict(source: dict[str, Any], *, allowed_keys: tuple[str, ...]) -> dict[str, Any]:
    return {
        key: source.get(key)
        for key in allowed_keys
        if source.get(key) not in (None, "", [], {}, ())
    }


class MemoryRetriever:
    def retrieve(
        self,
        memory,
        user_message: dict[str, Any],
        *,
        current_message_blocks: list[dict[str, Any]] | tuple[dict[str, Any], ...] = (),
        reference_message_blocks: list[dict[str, Any]] | tuple[dict[str, Any], ...] = (),
        limit: int = 6,
    ) -> list[RetrievedMemory]:
        has_text_block = any(
            isinstance(block, dict)
            and str(block.get("type", "") or "").strip() == "input_text"
            and str(block.get("text", "") or "").strip()
            for block in list(user_message.get("content") or [])
        )
        results: list[RetrievedMemory] = []

        compact_education = _trim_dict(
            dict(memory.education_state or {}),
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
        )
        if compact_education:
            results.append(
                RetrievedMemory(
                    kind="education_state",
                    name="education_continuity",
                    content=compact_education,
                    reason="active_session_state",
                    score=0.95 if has_text_block else 0.6,
                )
            )

        target = current_message_blocks or reference_message_blocks
        if target:
            analysis = memory.cached_or_metadata_block_analysis(target)
            if analysis:
                results.append(
                    RetrievedMemory(
                        kind="message_block",
                        name=memory.block_bundle_key(target),
                        content=MessageBlockMemoryEntry(
                            block_bundle_key=memory.block_bundle_key(target),
                            analysis=dict(analysis or {}),
                        ).to_payload(),
                        reason="message_block_context",
                        score=0.98,
                    )
                )

        if memory.context_summary and has_text_block:
            results.append(
                RetrievedMemory(
                    kind="summary",
                    name="context_summary",
                    content=memory.context_summary,
                    reason="session_summary",
                    score=0.35,
                )
            )

        if memory.multimodal_context_summary and target:
            results.append(
                RetrievedMemory(
                    kind="summary",
                    name="multimodal_context_summary",
                    content=memory.multimodal_context_summary,
                    reason="multimodal_summary",
                    score=0.5,
                )
            )

        results.sort(key=lambda item: float(item.score), reverse=True)
        return results[: max(1, int(limit or 6))]
