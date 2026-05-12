"""Domain-level context snapshots shared across application services."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ava.domain.multimodal.media import MediaArtifact, TurnInput


@dataclass(frozen=True)
class ContextSnapshot:
    turn_input: TurnInput
    user_text: str
    session_id: str
    session_scene: str
    turn_scene: str
    history_messages: list[dict[str, Any]]
    artifacts: tuple[MediaArtifact, ...]
    reference_artifacts: tuple[MediaArtifact, ...]
    turn_records: list[dict[str, Any]]
    context_profile: str = "full"
    reference_artifacts_inherited: bool = False
    router_artifact_brief: dict[str, Any] = field(default_factory=dict)
    router_plan: dict[str, Any] = field(default_factory=dict)
