from typing import Any


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


def record_to_history_messages(record: dict[str, object]) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    user_text = str(record.get("user_text", "") or "").strip()
    multimodal_summary = str(record.get("multimodal_summary", "") or "").strip()
    artifact_lines = _artifact_labels(list(record.get("artifacts") or []))

    if user_text and artifact_lines:
        user_content = f"{user_text}\n参考附件：\n" + "\n".join(f"- {label}" for label in artifact_lines)
    elif user_text:
        user_content = user_text
    elif artifact_lines:
        user_content = "参考附件：\n" + "\n".join(f"- {label}" for label in artifact_lines)
    else:
        user_content = multimodal_summary

    if user_content:
        messages.append({"role": "user", "content": user_content})

    turn_status = str(record.get("turn_status", "completed") or "completed").strip()
    assistant_text = (
        str(record.get("assistant_text", "") or "").strip()
        if turn_status in {"completed", "interrupted"}
        else ""
    )
    if assistant_text:
        messages.append({"role": "assistant", "content": assistant_text})
    return messages


def build_visible_history(
    turn_records: list[dict[str, Any]],
    *,
    max_messages: int,
) -> list[dict[str, Any]]:
    flattened: list[dict[str, Any]] = []
    for record in turn_records:
        flattened.extend(record_to_history_messages(record))
    return flattened[-max_messages:]
