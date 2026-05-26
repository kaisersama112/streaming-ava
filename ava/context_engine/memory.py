"""Bridge helpers from context engine to the domain memory module."""

from __future__ import annotations

from ava.domain.conversation.state import ConversationState
from ava.domain.multimodal import MediaArtifact, TurnInput


def retrieve_relevant_memories(
    state: ConversationState,
    turn_input: TurnInput,
    *,
    current_artifacts: tuple[MediaArtifact, ...] = (),
    reference_artifacts: tuple[MediaArtifact, ...] = (),
    limit: int = 6,
) -> list[dict]:
    return [
        item.to_payload()
        for item in state.memory.retrieve_relevant_memories(
            turn_input,
            current_artifacts=current_artifacts,
            reference_artifacts=reference_artifacts,
            limit=limit,
        )
    ]


def build_memory_projection(
    state: ConversationState,
    *,
    profile: str,
    turn_input: TurnInput,
    current_artifacts: tuple[MediaArtifact, ...] = (),
    reference_artifacts: tuple[MediaArtifact, ...] = (),
) -> dict:
    return state.memory.build_projection(
        turn_input,
        profile=profile,
        current_artifacts=current_artifacts,
        reference_artifacts=reference_artifacts,
    ).to_payload()
