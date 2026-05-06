"""Builds a compact snapshot of state for routing and response generation."""

from __future__ import annotations

import re

from ava.domain.session.state import ConversationState

from .media import TurnInput
from .models import ContextSnapshot
from .summary import summarize_history

_REFERENCE_FOLLOWUP_PATTERNS = (
    r"(^|[\s，。？！、])(这题|这个|这张图|这幅图|上题|上一题|刚才|前面|继续|接着|第二问|下一步|上一步)",
    r"(继续|接着)(说|讲|看|分析|做|答)",
)
_REFERENCE_FOLLOWUP_CUES = (
    "这题",
    "这个",
    "这张图",
    "这幅图",
    "上题",
    "上一题",
    "刚才",
    "前面",
    "继续",
    "接着",
    "第二问",
    "下一步",
    "上一步",
)
_REFERENCE_TOPIC_SWITCH_CUES = (
    "换一个",
    "换一道题",
    "换个问题",
    "别讲这个了",
    "我问个别的",
    "现在说另外一个",
    "换到",
)


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
        user_content = f"{user_text}\n参考附件:\n" + "\n".join(f"- {label}" for label in artifact_lines)
    elif user_text:
        user_content = user_text
    elif artifact_lines:
        user_content = "参考附件:\n" + "\n".join(f"- {label}" for label in artifact_lines)
    else:
        user_content = multimodal_summary

    if user_content:
        messages.append({"role": "user", "content": user_content})

    turn_status = str(record.get("turn_status", "completed") or "completed").strip()
    assistant_text = str(record.get("assistant_text", "") or "").strip() if turn_status == "completed" else ""
    if assistant_text:
        messages.append({"role": "assistant", "content": assistant_text})

    return messages


def _should_inherit_reference_artifacts(
    state: ConversationState,
    turn_input: TurnInput,
) -> bool:
    if turn_input.artifacts:
        return False

    text = (turn_input.normalized_text() or "").strip().lower()
    if not text:
        return False

    if any(token in text for token in _REFERENCE_TOPIC_SWITCH_CUES):
        return False

    if any(token in text for token in _REFERENCE_FOLLOWUP_CUES):
        return True

    if any(re.search(pattern, text) for pattern in _REFERENCE_FOLLOWUP_PATTERNS):
        return True

    previous_strategy_id = str(state.education_state.get("previous_strategy_id") or "").strip()
    previous_policy_id = str(state.education_state.get("previous_policy_id") or "").strip()
    learning_scenario = str(state.education_state.get("learning_scenario") or "").strip()
    if previous_strategy_id and len(text) <= 12:
        return True
    if (learning_scenario == "lesson" or previous_policy_id.startswith("lesson.")) and len(text) <= 24:
        return True

    return False


def _artifact_brief_for_context(
    state: ConversationState,
    *,
    current_artifacts,
    reference_artifacts,
) -> dict[str, object]:
    target_artifacts = current_artifacts or reference_artifacts
    if not target_artifacts:
        return {}
    return state.cached_or_metadata_artifact_analysis(target_artifacts)


def assemble_context(
    state: ConversationState,
    turn_input: TurnInput | str,
    history_window: int,
    current_turn_id: int | None = None,
    max_context_messages: int | None = None,
    profile: str = "full",
    include_reference_artifacts: bool | None = None,
) -> ContextSnapshot:
    if isinstance(turn_input, str):
        turn_input = TurnInput(text=turn_input)

    max_messages = max(2, int(max_context_messages or (history_window * 2)))
    include_history_messages = True
    include_recent_turns_summary = profile != "responder_minimal"
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
    sanitized_history = flattened_history[-max_messages:] if include_history_messages else []
    summary_source = flattened_history[-max_messages:]
    summary = summarize_history(summary_source, max_messages=max_messages)
    recent_turns_summary = state._summarize_turn_records(turn_records) if include_recent_turns_summary else ""
    user_text = turn_input.normalized_text() or turn_input.multimodal_summary()
    allow_reference_artifacts = (
        _should_inherit_reference_artifacts(state, turn_input)
        if include_reference_artifacts is None
        else bool(include_reference_artifacts)
    )
    reference_artifacts = ()
    if allow_reference_artifacts and not turn_input.artifacts:
        reference_artifacts = state.recent_reference_artifacts(current_turn_id=current_turn_id, limit_turns=1)
    artifact_brief = _artifact_brief_for_context(
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
        recent_history_summary=summary,
        education_state=dict(state.education_state),
        facts=dict(state.facts),
        history_messages=sanitized_history,
        multimodal_summary=turn_input.multimodal_summary(),
        recent_turns_summary=recent_turns_summary,
        artifacts=turn_input.artifacts,
        reference_artifacts=reference_artifacts,
        turn_records=turn_records,
        context_profile=profile,
        reference_artifacts_inherited=bool(reference_artifacts),
        router_artifact_brief=artifact_brief,
        router_text_brief={},
        router_plan={},
    )
