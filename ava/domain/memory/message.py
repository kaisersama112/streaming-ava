"""memory 层使用的标准 user message 辅助函数。"""

from __future__ import annotations

from typing import Any


def user_message_text(user_message: dict[str, Any] | None) -> str:
    """提取标准 user message 中的纯文本内容。"""
    if not isinstance(user_message, dict):
        return ""
    parts: list[str] = []
    for block in list(user_message.get("content") or []):
        if not isinstance(block, dict):
            continue
        if str(block.get("type", "") or "").strip() != "input_text":
            continue
        text = str(block.get("text", "") or "").strip()
        if text:
            parts.append(text)
    return "\n".join(parts).strip()


def user_message_has_non_text_blocks(user_message: dict[str, Any] | None) -> bool:
    """判断标准 user message 是否包含非文本输入块。"""
    if not isinstance(user_message, dict):
        return False
    return any(
        isinstance(block, dict) and str(block.get("type", "") or "").strip() != "input_text"
        for block in list(user_message.get("content") or [])
    )


def user_message_summary(user_message: dict[str, Any] | None) -> str:
    """生成标准 user message 的轻量摘要。"""
    if not isinstance(user_message, dict):
        return ""
    text_value = user_message_text(user_message)
    labels: list[str] = []
    for index, block in enumerate(list(user_message.get("content") or []), start=1):
        if not isinstance(block, dict):
            continue
        block_type = str(block.get("type", "") or "").strip()
        if block_type == "input_text":
            continue
        if block_type == "input_image":
            labels.append(f"[image] image-{index}")
            continue
        if block_type == "input_audio":
            labels.append(f"[audio] audio-{index}")
            continue
        if block_type == "input_file":
            name = str(block.get("filename", "") or f"file-{index}").strip()
            labels.append(f"[file] {name}")
    if text_value and labels:
        return f"{text_value}\n" + "\n".join(labels)
    if text_value:
        return text_value
    return "\n".join(labels).strip()
