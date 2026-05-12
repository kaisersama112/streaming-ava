"""Build context snapshots for routing and responding."""

from __future__ import annotations

from ava.core.context.continuity import (
    build_artifact_brief_for_context,
    should_inherit_reference_artifacts,
)
from ava.core.context.input import build_turn_input
from ava.domain.multimodal.media import TurnInput
from ava.domain.conversation.models import ContextSnapshot
from ava.domain.conversation.state import ConversationState


def _artifact_labels(raw_artifacts: list[dict[str, object]]) -> list[str]:
    labels: list[str] = []
    for artifact in raw_artifacts:
        kind = str(artifact.get("kind", "file") or "file").strip()
        name = str(artifact.get("name", "") or "").strip()
        summary = str(artifact.get("summary", "") or "").strip()
        base = f"[{kind}] {name}".strip()
        if summary and summary != name:
            labels.append(f"{base}: {summary}" if base else summary)
        elif base:
            labels.append(base)
    return labels


def _record_to_history_messages(record: dict[str, object]) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    user_text = str(record.get("user_text", "") or "").strip()
    multimodal_summary = str(record.get("multimodal_summary", "") or "").strip()
    artifact_lines = _artifact_labels(list(record.get("artifacts") or []))

    if user_text and artifact_lines:
        user_content = (
                f"{user_text}\n参考附件：\n"
                + "\n".join(f"- {label}" for label in artifact_lines)
        )
    elif user_text:
        user_content = user_text
    elif artifact_lines:
        user_content = (
                "参考附件：\n"
                + "\n".join(f"- {label}" for label in artifact_lines)
        )
    else:
        user_content = multimodal_summary

    if user_content:
        messages.append({"role": "user", "content": user_content})

    turn_status = str(record.get("turn_status", "completed") or "completed").strip()
    assistant_text = str(record.get("assistant_text", "") or "").strip() if turn_status == "completed" else ""
    if assistant_text:
        messages.append({"role": "assistant", "content": assistant_text})

    return messages


def build_context_snapshot(
    state: ConversationState,
    turn_input: TurnInput | str,
    history_window: int,
    current_turn_id: int | None = None,
    max_context_messages: int | None = None,
    profile: str = "full",
    include_reference_artifacts: bool | None = None,
) -> ContextSnapshot:
    if isinstance(turn_input, str):
        turn_input = build_turn_input(turn_input)

    max_messages = max(2, int(max_context_messages or (history_window * 2)))
    if current_turn_id is None:
        turn_records = state.turn_records[-max_messages:]
    else:
        turn_records = [
            item
            for item in state.turn_records
            if item.get("turn_id") != current_turn_id
        ][-max_messages:]

    flattened_history: list[dict[str, str]] = []
    for record in turn_records:
        flattened_history.extend(_record_to_history_messages(record))
    sanitized_history = flattened_history[-max_messages:]
    user_text = turn_input.normalized_text() or turn_input.multimodal_summary()
    allow_reference_artifacts = (
        should_inherit_reference_artifacts(state, turn_input)
        if include_reference_artifacts is None
        else bool(include_reference_artifacts)
    )
    reference_artifacts = ()
    if allow_reference_artifacts and not turn_input.artifacts:
        reference_artifacts = state.recent_reference_artifacts(current_turn_id=current_turn_id, limit_turns=1)
    artifact_brief = build_artifact_brief_for_context(
        state,
        current_artifacts=turn_input.artifacts,
        reference_artifacts=reference_artifacts,
    )
    return ContextSnapshot(
        turn_input=turn_input,
        user_text=user_text,
        session_id=state.session_id,
        session_scene=state.session_scene,
        turn_scene=state.turn_scene,
        history_messages=sanitized_history,
        artifacts=turn_input.artifacts,
        reference_artifacts=reference_artifacts,
        turn_records=turn_records,
        context_profile=profile,
        reference_artifacts_inherited=bool(reference_artifacts),
        router_artifact_brief=artifact_brief,
        router_plan={},
    )

