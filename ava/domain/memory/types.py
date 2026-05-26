"""Structured types for the memory module."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class RetrievedMemory:
    kind: str
    name: str
    content: Any
    reason: str
    score: float

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ArtifactMemoryEntry:
    artifact_bundle_key: str
    analysis: dict[str, Any]

    def to_payload(self) -> dict[str, Any]:
        return {
            "artifact_bundle_key": self.artifact_bundle_key,
            "analysis": dict(self.analysis or {}),
        }


@dataclass(frozen=True)
class MemoryProjection:
    recent_topics: list[str] = field(default_factory=list)
    context_summary: str = ""
    multimodal_context_summary: str = ""
    education_state: dict[str, Any] = field(default_factory=dict)
    artifact_memory: list[dict[str, Any]] = field(default_factory=list)
    retrieved_memories: list[dict[str, Any]] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        return {
            "recent_topics": list(self.recent_topics or []),
            "context_summary": str(self.context_summary or "").strip(),
            "multimodal_context_summary": str(self.multimodal_context_summary or "").strip(),
            "education_state": dict(self.education_state or {}),
            "artifact_memory": [dict(item or {}) for item in (self.artifact_memory or [])],
            "retrieved_memories": [dict(item or {}) for item in (self.retrieved_memories or [])],
        }
