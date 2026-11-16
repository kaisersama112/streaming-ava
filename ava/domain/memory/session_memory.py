"""Memory aggregate root and public memory API."""

from __future__ import annotations

from typing import Any

from ava.domain.memory.message_blocks import MessageBlockMemoryStore
from ava.domain.memory.education import EducationMemory
from ava.domain.memory.projector import MemoryProjector
from ava.domain.memory.retriever import MemoryRetriever
from ava.domain.memory.summaries import SummaryMemory
from ava.domain.memory.types import MemoryProjection, RetrievedMemory


class SessionMemory:
    def __init__(self, memory_size: int = 8) -> None:
        self.memory_size = max(1, int(memory_size or 8))
        self.education_memory = EducationMemory()
        self.message_block_store = MessageBlockMemoryStore()
        self.summary_memory = SummaryMemory(self.memory_size)
        self.retriever = MemoryRetriever()
        self.projector = MemoryProjector()
        self.user_facts: dict[str, str] = {}

    def set_user_fact(self, key: str, value: str) -> None:
        fact_key = str(key or "").strip()[:40]
        fact_value = str(value or "").strip()[:160]
        if not fact_key or not fact_value:
            return
        if len(self.user_facts) >= 24 and fact_key not in self.user_facts:
            self.user_facts.pop(next(iter(self.user_facts)), None)
        self.user_facts[fact_key] = fact_value

    @property
    def education_state(self) -> dict[str, Any]:
        return self.education_memory.state

    @property
    def recent_topics(self) -> list[str]:
        return list(self.summary_memory.recent_topics)

    @property
    def context_summary(self) -> str:
        return self.summary_memory.context_summary

    @property
    def multimodal_context_summary(self) -> str:
        return self.summary_memory.multimodal_context_summary

    @property
    def message_block_analysis_cache(self) -> dict[str, dict[str, Any]]:
        return self.message_block_store.cache

    def reset(self) -> None:
        self.education_memory.reset()
        self.message_block_store.reset()
        self.summary_memory.reset()
        self.user_facts = {}

    def to_payload(
        self,
        *,
        turn_records: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            **self.summary_memory.to_payload(turn_records=turn_records),
            "message_block_analysis_cache": self.message_block_store.to_payload(),
            "education_state": self.education_memory.to_payload(),
            "user_facts": dict(self.user_facts),
        }

    def load_payload(
        self,
        data: dict[str, Any],
        *,
        turn_records: list[dict[str, Any]],
    ) -> None:
        payload = dict(data.get("memory") or {})
        self.summary_memory.load_payload(payload, turn_records=turn_records)
        self.message_block_store.load_payload(payload.get("message_block_analysis_cache"))
        self.education_memory.load_payload(payload.get("education_state"))
        self.user_facts = {
            str(key).strip()[:40]: str(value).strip()[:160]
            for key, value in dict(payload.get("user_facts") or {}).items()
            if str(key or "").strip() and str(value or "").strip()
        }

    def refresh_summaries(
        self,
        *,
        turn_records: list[dict[str, Any]],
    ) -> None:
        self.summary_memory.refresh(turn_records=turn_records)

    def append_recent_topic(self, text: str) -> None:
        self.summary_memory.append_recent_topic(text)

    @staticmethod
    def _truncate_text(text: str, limit: int) -> str:
        value = str(text or "").strip()
        if len(value) <= limit:
            return value
        return value[:limit].rstrip() + "..."

    def apply_route_transition(self, *, should_preserve_teaching_state: bool) -> None:
        self.education_memory.apply_route_transition(
            should_preserve_teaching_state=should_preserve_teaching_state
        )

    def update_education_state_from_strategy(
        self,
        strategy: dict[str, Any] | None,
        *,
        user_message: dict[str, Any] | None = None,
    ) -> None:
        self.education_memory.update_from_strategy(strategy, user_message=user_message)

    def set_education_state_value(self, key: str, value: Any) -> None:
        self.education_memory.set_value(key, value)

    def block_bundle_key(
        self,
        message_blocks: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    ) -> str:
        return self.message_block_store.block_bundle_key(message_blocks)

    def cached_block_analysis(
        self,
        message_blocks: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    ) -> dict[str, Any]:
        return self.message_block_store.cached_block_analysis(message_blocks)

    def cached_or_metadata_block_analysis(
        self,
        message_blocks: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    ) -> dict[str, Any]:
        return self.message_block_store.cached_or_metadata_block_analysis(message_blocks)

    def remember_block_analysis(
        self,
        message_blocks: list[dict[str, Any]] | tuple[dict[str, Any], ...],
        analysis: dict[str, Any],
    ) -> None:
        self.message_block_store.remember_block_analysis(message_blocks, analysis)

    def retrieve_relevant_memories(
        self,
        user_message: dict[str, Any],
        *,
        current_message_blocks: list[dict[str, Any]] | tuple[dict[str, Any], ...] = (),
        reference_message_blocks: list[dict[str, Any]] | tuple[dict[str, Any], ...] = (),
        limit: int = 6,
    ) -> list[RetrievedMemory]:
        return self.retriever.retrieve(
            self,
            user_message,
            current_message_blocks=current_message_blocks,
            reference_message_blocks=reference_message_blocks,
            limit=limit,
        )

    def build_projection(
        self,
        user_message: dict[str, Any],
        *,
        profile: str,
        current_message_blocks: list[dict[str, Any]] | tuple[dict[str, Any], ...] = (),
        reference_message_blocks: list[dict[str, Any]] | tuple[dict[str, Any], ...] = (),
    ) -> MemoryProjection:
        return self.projector.build(
            self,
            user_message,
            profile=profile,
            current_message_blocks=current_message_blocks,
            reference_message_blocks=reference_message_blocks,
        )

    def to_debug_payload(self) -> dict[str, Any]:
        return {
            "recent_topics": list(self.recent_topics),
            "context_summary": self.context_summary,
            "multimodal_context_summary": self.multimodal_context_summary,
            "education_state": dict(self.education_state),
            "user_facts": dict(self.user_facts),
            "message_block_analysis_cache_size": len(self.message_block_analysis_cache),
        }
