"""Utilities for compressing recent history into a router-friendly summary."""

from __future__ import annotations

from typing import Any


def _clip(text: str, limit: int = 48) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        pieces: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text":
                pieces.append(str(item.get("text", "")))
            elif item.get("type") == "image_url":
                pieces.append("[image]")
            elif item.get("type") == "input_audio":
                pieces.append("[audio]")
            elif item.get("type") == "video":
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
