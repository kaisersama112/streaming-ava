"""Memory aggregate root and public memory API."""

from __future__ import annotations

from typing import Any

from ava.domain.memory.artifacts import ArtifactMemoryStore
from ava.domain.memory.education import EducationMemory
from ava.domain.memory.projector import MemoryProjector
from ava.domain.memory.retriever import MemoryRetriever
from ava.domain.memory.summaries import SummaryMemory
from ava.domain.memory.types import MemoryProjection, RetrievedMemory
from ava.domain.multimodal import MediaArtifact, TurnInput


class SessionMemory:
    def __init__(self, memory_size: int = 8) -> None:
        self.memory_size = max(1, int(memory_size or 8))
        self.education_memory = EducationMemory()
        self.artifact_store = ArtifactMemoryStore()
        self.summary_memory = SummaryMemory(self.memory_size)
        self.retriever = MemoryRetriever()
        self.projector = MemoryProjector()

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
    def artifact_analysis_cache(self) -> dict[str, dict[str, Any]]:
        return self.artifact_store.cache

    def reset(self) -> None:
        self.education_memory.reset()
        self.artifact_store.reset()
        self.summary_memory.reset()

    def to_payload(
        self,
        *,
        turn_records: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            **self.summary_memory.to_payload(turn_records=turn_records),
            "artifact_analysis_cache": self.artifact_store.to_payload(),
            "education_state": self.education_memory.to_payload(),
        }

    def load_payload(
        self,
        data: dict[str, Any],
        *,
        turn_records: list[dict[str, Any]],
    ) -> None:
        payload = dict(data.get("memory") or {})
        self.summary_memory.load_payload(payload, turn_records=turn_records)
        self.artifact_store.load_payload(payload.get("artifact_analysis_cache"))
        self.education_memory.load_payload(payload.get("education_state"))

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

    def update_education_state_from_text(self, user_text: str) -> None:
        self.education_memory.update_from_text(user_text)

    def update_education_state_from_strategy(
        self,
        strategy: dict[str, Any] | None,
        *,
        turn_input: TurnInput | None = None,
    ) -> None:
        self.education_memory.update_from_strategy(strategy, turn_input=turn_input)

    def set_education_state_value(self, key: str, value: Any) -> None:
        self.education_memory.set_value(key, value)

    def artifact_bundle_key(
        self,
        artifacts: tuple[MediaArtifact, ...] | list[MediaArtifact] | list[dict[str, Any]],
    ) -> str:
        return self.artifact_store.artifact_bundle_key(artifacts)

    def cached_artifact_analysis(
        self,
        artifacts: tuple[MediaArtifact, ...] | list[MediaArtifact],
    ) -> dict[str, Any]:
        return self.artifact_store.cached_artifact_analysis(artifacts)

    def cached_or_metadata_artifact_analysis(
        self,
        artifacts: tuple[MediaArtifact, ...] | list[MediaArtifact],
    ) -> dict[str, Any]:
        return self.artifact_store.cached_or_metadata_artifact_analysis(artifacts)

    def remember_artifact_analysis(
        self,
        artifacts: tuple[MediaArtifact, ...] | list[MediaArtifact],
        analysis: dict[str, Any],
    ) -> None:
        self.artifact_store.remember_artifact_analysis(artifacts, analysis)

    def retrieve_relevant_memories(
        self,
        turn_input: TurnInput,
        *,
        current_artifacts: tuple[MediaArtifact, ...] = (),
        reference_artifacts: tuple[MediaArtifact, ...] = (),
        limit: int = 6,
    ) -> list[RetrievedMemory]:
        return self.retriever.retrieve(
            self,
            turn_input,
            current_artifacts=current_artifacts,
            reference_artifacts=reference_artifacts,
            limit=limit,
        )

    def build_projection(
        self,
        turn_input: TurnInput,
        *,
        profile: str,
        current_artifacts: tuple[MediaArtifact, ...] = (),
        reference_artifacts: tuple[MediaArtifact, ...] = (),
    ) -> MemoryProjection:
        return self.projector.build(
            self,
            turn_input,
            profile=profile,
            current_artifacts=current_artifacts,
            reference_artifacts=reference_artifacts,
        )

    def to_debug_payload(self) -> dict[str, Any]:
        return {
            "recent_topics": list(self.recent_topics),
            "context_summary": self.context_summary,
            "multimodal_context_summary": self.multimodal_context_summary,
            "education_state": dict(self.education_state),
            "artifact_analysis_cache_size": len(self.artifact_analysis_cache),
        }
