"""Session summaries derived from turn records."""

from __future__ import annotations

from collections import deque
from typing import Any

from ava.domain.conversation.summary import summarize_turn_records

_ARTIFACT_TYPES = {"input_image", "input_audio", "input_file"}


def _visual_turn_records(turn_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        record
        for record in turn_records
        if any(
            isinstance(block, dict) and str(block.get("type", "") or "").strip() in _ARTIFACT_TYPES
            for block in list((record.get("user_message") or {}).get("content") or [])
        )
    ]


class SummaryMemory:
    def __init__(self, memory_size: int) -> None:
        self.memory_size = max(1, int(memory_size or 8))
        self.recent_topics: deque[str] = deque(maxlen=self.memory_size)
        self.context_summary: str = "无"
        self.multimodal_context_summary: str = "无"

    def reset(self) -> None:
        self.recent_topics = deque(maxlen=self.memory_size)
        self.context_summary = "无"
        self.multimodal_context_summary = "无"

    def load_payload(self, payload: dict | None, *, turn_records: list[dict]) -> None:
        source = dict(payload or {})
        self.recent_topics = deque(
            [str(item) for item in (source.get("recent_topics") or []) if str(item).strip()],
            maxlen=self.memory_size,
        )
        self.refresh(turn_records=turn_records)

    def to_payload(self, *, turn_records: list[dict]) -> dict:
        return {
            "recent_topics": list(self.recent_topics),
            "context_summary": summarize_turn_records(
                turn_records[-self.memory_size :],
                max_turns=self.memory_size,
            ),
            "multimodal_context_summary": summarize_turn_records(
                _visual_turn_records(turn_records)[-self.memory_size :],
                max_turns=self.memory_size,
            ),
        }

    def refresh(self, *, turn_records: list[dict]) -> None:
        self.context_summary = summarize_turn_records(
            turn_records[-self.memory_size :],
            max_turns=self.memory_size,
        )
        self.multimodal_context_summary = summarize_turn_records(
            _visual_turn_records(turn_records)[-self.memory_size :],
            max_turns=self.memory_size,
        )

    def append_recent_topic(self, text: str) -> None:
        value = str(text or "").strip()
        if value:
            self.recent_topics.append(value[:24])
