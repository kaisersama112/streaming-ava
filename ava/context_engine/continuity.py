"""Continuity heuristics shared by router and responder context assembly."""

from __future__ import annotations

from ava.context_engine.types import ContextSnapshot
from ava.domain.conversation.state import ConversationState
from ava.domain.multimodal import TurnInput


def should_inherit_reference_artifacts(
    state: ConversationState,
    turn_input: TurnInput,
) -> bool:
    """Decide whether the current turn should inherit prior reference media."""

    if turn_input.artifacts:
        return False

    text = (turn_input.normalized_text() or "").strip().lower()
    if not text:
        return False

    previous_strategy_id = str(state.memory.education_state.get("previous_strategy_id") or "").strip()
    previous_policy_id = str(state.memory.education_state.get("previous_policy_id") or "").strip()
    learning_scenario = str(state.memory.education_state.get("learning_scenario") or "").strip()

    if previous_strategy_id and len(text) <= 12:
        return True

    if (learning_scenario == "lesson" or previous_policy_id.startswith("lesson.")) and len(text) <= 24:
        return True

    return False


def build_artifact_brief_for_context(
    state: ConversationState,
    *,
    current_artifacts,
    reference_artifacts,
) -> dict[str, object]:
    """Return cached or metadata-derived artifact analysis for this turn."""

    target_artifacts = current_artifacts or reference_artifacts
    if not target_artifacts:
        return {}
    return state.memory.cached_or_metadata_artifact_analysis(target_artifacts)


def should_isolate_current_artifact_context(
    state: ConversationState,
    snapshot: ContextSnapshot,
    *,
    current_turn_id: int | None = None,
) -> bool:
    """Detect when a fresh artifact upload should start a new routing context."""

    current_artifacts = tuple(snapshot.artifacts or ())
    if not current_artifacts:
        return False

    previous_artifacts = state.recent_reference_artifacts(
        current_turn_id=current_turn_id,
        limit_turns=1,
    )
    if not previous_artifacts:
        return True

    current_key = state.memory.artifact_bundle_key(current_artifacts)
    previous_key = state.memory.artifact_bundle_key(previous_artifacts)
    if current_key and current_key == previous_key:
        return False
    return True


def select_router_model(
    snapshot: ContextSnapshot,
    *,
    text_only: bool,
    model: str,
    multimodal_model: str,
) -> str:
    """Select a text or multimodal router model for the current snapshot."""

    if text_only:
        return model
    if snapshot.artifacts or snapshot.reference_artifacts:
        return multimodal_model
    return model
