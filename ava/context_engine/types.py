"""Shared types for the unified context construction engine.

This package owns the model-visible context contract for router and responder
phases. Callers should depend on these types instead of assembling ad hoc
history, memory, and multimodal state on their own.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ava.domain.multimodal.media import MediaArtifact, TurnInput


@dataclass(frozen=True)
class ContextSnapshot:
    """Immutable context bundle consumed by routing and generation.

    The snapshot is the single source of truth for one-turn context assembly.
    It contains:
    - normalized current input
    - selected recent conversation history
    - current and inherited multimodal artifacts
    - router-side artifact reasoning
    - memory projection prepared for model consumption
    """

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
    memory_projection: dict[str, Any] = field(default_factory=dict)
    retrieved_memories: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class SnapshotCompileOptions:
    """Options for compiling one context snapshot."""

    history_window: int
    current_turn_id: int | None = None
    max_context_messages: int | None = None
    profile: str = "full"
    include_reference_artifacts: bool | None = None


@dataclass(frozen=True)
class CompiledContextEnvelope:
    """Compiled runtime artifact consumed by router or responder execution."""

    phase: str
    snapshot: ContextSnapshot
    instructions: str
    runtime_context: dict[str, Any]
    messages: list[dict[str, object]]
    active_skills: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CompiledInstructions:
    """Compiled high-priority instruction block for one model phase."""

    phase: str
    text: str
    active_skills: list[str] = field(default_factory=list)
    sections: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SkillSelection:
    """One activated skill fragment selected by the compiler."""

    skill_id: str
    title: str
    instruction_fragment: str
    source_kind: str = "builtin"
    source_path: str | None = None
