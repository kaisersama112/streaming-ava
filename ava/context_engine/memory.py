"""Memory projection and retrieval helpers for model-visible context."""

from __future__ import annotations

from typing import Any

from ava.domain.conversation.state import ConversationState
from ava.domain.multimodal import MediaArtifact, TurnInput


def _trim_dict(source: dict[str, Any], *, allowed_keys: tuple[str, ...]) -> dict[str, Any]:
    return {
        key: source.get(key)
        for key in allowed_keys
        if source.get(key) not in (None, "", [], {}, ())
    }


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return str(value)


def _artifact_memory(
    state: ConversationState,
    *,
    current_artifacts: tuple[MediaArtifact, ...],
    reference_artifacts: tuple[MediaArtifact, ...],
) -> list[dict[str, Any]]:
    """Project current or inherited artifact analysis into memory space."""

    target = current_artifacts or reference_artifacts
    if not target:
        return []
    analysis = state.memory.cached_or_metadata_artifact_analysis(target)
    if not analysis:
        return []
    return [
        {
            "artifact_bundle_key": state.memory.artifact_bundle_key(target),
            "analysis": _json_safe(analysis),
        }
    ]


def retrieve_relevant_memories(
    state: ConversationState,
    turn_input: TurnInput,
    *,
    current_artifacts: tuple[MediaArtifact, ...] = (),
    reference_artifacts: tuple[MediaArtifact, ...] = (),
    limit: int = 6,
) -> list[dict[str, Any]]:
    """Retrieve compact, prompt-safe memories related to the current turn.

    This first version intentionally stays lightweight:
    - prefer stable structured memory over speculative free-form recall
    - keep router-safe summaries small
    - surface artifact and education continuity signals explicitly
    """

    text = (turn_input.normalized_text() or turn_input.multimodal_summary() or "").strip().lower()
    results: list[dict[str, Any]] = []

    facts = dict(getattr(state.memory, "facts", {}) or {})
    for key, value in facts.items():
        score = 0.4
        reason = "stable_fact"
        lower_key = str(key).strip().lower()
        lower_value = str(value).strip().lower()
        if text and (lower_key in text or lower_value in text):
            score = 0.9
            reason = "matched_current_turn"
        results.append(
            {
                "kind": "fact",
                "name": str(key),
                "content": str(value),
                "reason": reason,
                "score": score,
            }
        )

    education_state = dict(getattr(state.memory, "education_state", {}) or {})
    compact_education = _trim_dict(
        education_state,
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
            {
                "kind": "education_state",
                "name": "education_continuity",
                "content": compact_education,
                "reason": "active_session_state",
                "score": 0.95 if text else 0.6,
            }
        )

    artifact_items = _artifact_memory(
        state,
        current_artifacts=current_artifacts,
        reference_artifacts=reference_artifacts,
    )
    for item in artifact_items:
        results.append(
            {
                "kind": "artifact",
                "name": item.get("artifact_bundle_key", ""),
                "content": item.get("analysis", {}),
                "reason": "artifact_context",
                "score": 0.98,
            }
        )

    context_summary = str(getattr(state.memory, "context_summary", "") or "").strip()
    if context_summary and text:
        results.append(
            {
                "kind": "summary",
                "name": "context_summary",
                "content": context_summary,
                "reason": "session_summary",
                "score": 0.35,
            }
        )

    multimodal_summary = str(getattr(state.memory, "multimodal_context_summary", "") or "").strip()
    if multimodal_summary and (current_artifacts or reference_artifacts):
        results.append(
            {
                "kind": "summary",
                "name": "multimodal_context_summary",
                "content": multimodal_summary,
                "reason": "multimodal_summary",
                "score": 0.5,
            }
        )

    results.sort(key=lambda item: float(item.get("score", 0.0)), reverse=True)
    return results[: max(1, int(limit or 6))]


def build_memory_projection(
    state: ConversationState,
    *,
    profile: str,
    turn_input: TurnInput,
    current_artifacts: tuple[MediaArtifact, ...] = (),
    reference_artifacts: tuple[MediaArtifact, ...] = (),
) -> dict[str, Any]:
    """Build the model-visible memory block for a specific context profile."""

    memory = state.memory
    retrieved_memories = retrieve_relevant_memories(
        state,
        turn_input,
        current_artifacts=current_artifacts,
        reference_artifacts=reference_artifacts,
    )
    base_projection = {
        "facts": dict(getattr(memory, "facts", {}) or {}),
        "recent_topics": list(getattr(memory, "recent_topics", []) or []),
        "context_summary": str(getattr(memory, "context_summary", "") or "").strip(),
        "multimodal_context_summary": str(getattr(memory, "multimodal_context_summary", "") or "").strip(),
        "education_state": dict(getattr(memory, "education_state", {}) or {}),
        "artifact_memory": _artifact_memory(
            state,
            current_artifacts=current_artifacts,
            reference_artifacts=reference_artifacts,
        ),
        "retrieved_memories": [_json_safe(item) for item in retrieved_memories],
    }

    if profile == "router":
        return {
            "recent_topics": list(base_projection["recent_topics"])[:4],
            "education_state": _trim_dict(
                dict(base_projection["education_state"]),
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
            ),
            "artifact_memory": list(base_projection["artifact_memory"])[:1],
            "retrieved_memories": list(base_projection["retrieved_memories"])[:3],
        }

    return base_projection
