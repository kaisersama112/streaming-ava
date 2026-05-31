"""Utilities for compressing conversation records into compact summaries."""

from __future__ import annotations

from typing import Any


def _clip(text: str, limit: int = 48) -> str:
    normalized = " ".join(str(text or "").split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1] + "…"


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        pieces: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            item_type = str(item.get("type", "") or "").strip()
            if item_type in {"text", "input_text"}:
                pieces.append(str(item.get("text", "")))
            elif item_type in {"image_url", "input_image"}:
                pieces.append("[image]")
            elif item_type == "input_audio":
                pieces.append("[audio]")
            elif item_type == "video":
                pieces.append("[video]")
        return " ".join(piece for piece in pieces if piece).strip()
    if isinstance(content, dict):
        if "text" in content:
            return str(content.get("text", ""))
        return str(content)
    return str(content)


def summarize_history(history: list[dict[str, Any]], max_messages: int = 8) -> str:
    recent = history[-max_messages:]
    if not recent:
        return "无"

    lines: list[str] = []
    for item in recent:
        role = "用户" if item.get("role") == "user" else "助手"
        content = _clip(_content_to_text(item.get("content", "")))
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines) if lines else "无"


def summarize_turn_records(turn_records: list[dict[str, Any]], max_turns: int = 4) -> str:
    recent = turn_records[-max_turns:]
    if not recent:
        return "无"

    lines: list[str] = []
    for record in recent:
        user_message = dict(record.get("user_message") or {})
        assistant_message = dict(record.get("assistant_message") or {})
        user_text = _content_to_text(user_message.get("content", ""))
        assistant_text = _content_to_text(assistant_message.get("content", ""))
        turn_status = str(record.get("turn_status", "completed") or "completed").strip()
        label = str(user_text or "").strip()
        if not label:
            continue
        if assistant_text and turn_status == "completed":
            lines.append(f"用户: {_clip(label, 80)}\n助手: {_clip(assistant_text, 80)}")
        else:
            lines.append(f"用户: {_clip(label, 80)}")
    return "\n".join(lines) if lines else "无"
