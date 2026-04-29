"""Domain-level context snapshots shared across application services."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .media import MediaArtifact, TurnInput


@dataclass(frozen=True)
class ContextSnapshot:
    turn_input: TurnInput
    user_text: str
    session_id: str
    session_scene: str
    turn_scene: str
    recent_history_summary: str
    education_state: dict[str, Any]
    facts: dict[str, Any]
    history_messages: list[dict[str, Any]]
    multimodal_summary: str
    recent_turns_summary: str
    artifacts: tuple[MediaArtifact, ...]
    reference_artifacts: tuple[MediaArtifact, ...]
    turn_records: list[dict[str, Any]]
    context_profile: str = "full"
    reference_artifacts_inherited: bool = False
    router_artifact_brief: dict[str, Any] = field(default_factory=dict)
    router_text_brief: dict[str, Any] = field(default_factory=dict)
    router_plan: dict[str, Any] = field(default_factory=dict)
