"""多模态引用继承与上下文隔离判断。

解决两类问题：
- 新附件误继承旧上下文：当前轮出现新的图片/音视频 artifact 时，切断旧视觉引用
- 连续追问需保留视觉上下文：纯文字追问且最近轮存在视觉 artifact 时，继承其摘要（带来源 turn_id）
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

ARTIFACT_BLOCK_TYPES = frozenset({"input_image", "input_audio", "input_file"})

_TOPIC_SWITCH_PATTERN = re.compile(
    r"(换个话题|换一题|下一题|换个题|不说这个|别讲这个|换张图|换个图片|新问题|换个问题)"
)


def artifact_blocks(message: dict[str, Any] | None) -> list[dict[str, Any]]:
    """提取标准消息中的非文本 artifact 块。"""
    return [
        dict(block)
        for block in list((message or {}).get("content") or [])
        if isinstance(block, dict) and str(block.get("type", "") or "").strip() in ARTIFACT_BLOCK_TYPES
    ]


def has_artifacts(message: dict[str, Any] | None) -> bool:
    return bool(artifact_blocks(message))


def message_text(message: dict[str, Any] | None) -> str:
    parts = [
        str(block.get("text", "") or "").strip()
        for block in list((message or {}).get("content") or [])
        if isinstance(block, dict) and str(block.get("type", "") or "").strip() == "input_text"
    ]
    return "\n".join(part for part in parts if part).strip()


def block_reference_token(block: dict[str, Any]) -> str:
    """单个 artifact 的稳定引用指纹（不依赖 base64 全文，避免大对象哈希开销）。"""
    block_type = str(block.get("type", "") or "").strip()
    if block_type == "input_image":
        ref = str(block.get("image_url", "") or "")
    elif block_type == "input_audio":
        payload = dict(block.get("input_audio") or {})
        ref = f"audio:{payload.get('format', '')}:{len(str(payload.get('data', '') or ''))}:{str(payload.get('data', '') or '')[:64]}"
    else:
        ref = str(block.get("file_id") or block.get("file_url") or block.get("file_data") or block.get("filename") or "")
    if ref.startswith("data:"):
        head, _, tail = ref.partition(",")
        ref = f"{head}:{len(tail)}:{tail[:48]}"
    return f"{block_type}:{hashlib.sha256(ref.encode('utf-8', errors='ignore')).hexdigest()[:16]}"


def context_isolation_token(message: dict[str, Any] | None) -> str:
    """当前轮视觉上下文隔离 token：跨轮引用需 token 匹配或显式继承。"""
    tokens = sorted(block_reference_token(block) for block in artifact_blocks(message))
    if not tokens:
        return ""
    return hashlib.sha256("|".join(tokens).encode("utf-8")).hexdigest()[:16]


def _artifact_name(block: dict[str, Any]) -> str:
    block_type = str(block.get("type", "") or "").strip()
    if block_type == "input_image":
        url = str(block.get("image_url", "") or "")
        if url.startswith("data:"):
            return "inline-image"
        path = urlparse(url).path
        return path.rsplit("/", 1)[-1] or "image"
    if block_type == "input_audio":
        return f"audio.{dict(block.get('input_audio') or {}).get('format', 'wav')}"
    return str(block.get("filename") or "file").strip() or "file"


def blocks_to_artifacts(blocks: list[dict[str, Any]] | tuple[dict[str, Any], ...]) -> list[dict[str, Any]]:
    """把标准 content block 转成 MessageBlockMemoryStore 可缓存的 artifact 形状。"""
    artifacts: list[dict[str, Any]] = []
    for block in list(blocks or []):
        if not isinstance(block, dict):
            continue
        block_type = str(block.get("type", "") or "").strip()
        if block_type not in ARTIFACT_BLOCK_TYPES:
            continue
        kind = {"input_image": "image", "input_audio": "audio"}.get(block_type, "file")
        name = _artifact_name(block)
        if block_type == "input_file" and name.lower().endswith((".mp4", ".mov", ".avi", ".mkv", ".webm")):
            kind = "video"
        data_url = str(block.get("image_url", "") or "") if block_type == "input_image" else ""
        uri = str(block.get("file_url", "") or "") if block_type == "input_file" else ""
        artifacts.append(
            {
                "kind": kind,
                "name": name,
                "summary": name,
                "data_url": data_url,
                "uri": uri,
                "metadata": {"source_block_type": block_type, "reference_token": block_reference_token(block)},
            }
        )
    return artifacts


def last_visual_turn(
    turn_records: list[dict[str, Any]],
    *,
    max_turns: int = 2,
    exclude_turn_id: int | None = None,
) -> dict[str, Any] | None:
    """最近 max_turns 个已完成轮次中，最后一个带 artifact 的轮次。"""
    completed = [
        record
        for record in list(turn_records or [])
        if str(record.get("turn_status", "completed") or "completed").strip() == "completed"
        and record.get("turn_id") != exclude_turn_id
    ]
    for record in reversed(completed[-max(1, int(max_turns)):]):
        if has_artifacts(record.get("user_message")):
            return record
    return None


@dataclass(frozen=True)
class VisualContinuity:
    inherit: bool
    reason: str
    source_turn_id: int | None = None
    source_blocks: list[dict[str, Any]] | None = None
    isolation_token: str = ""


def should_inherit_visual_context(
    current_message: dict[str, Any] | None,
    turn_records: list[dict[str, Any]],
    *,
    max_turns: int = 2,
    exclude_turn_id: int | None = None,
) -> VisualContinuity:
    """引用继承真值表：

    - 当前轮有新 artifact → 不继承（隔离），token 取当前轮
    - 纯文字 + 明确换题/换话题 → 不继承
    - 纯文字追问 + 最近轮有 artifact → 继承该轮视觉摘要（带来源 turn_id）
    - 其它 → 不继承
    """
    current_blocks = artifact_blocks(current_message)
    token = context_isolation_token(current_message)
    if current_blocks:
        return VisualContinuity(inherit=False, reason="new_artifacts_isolated", isolation_token=token)
    text = message_text(current_message)
    if _TOPIC_SWITCH_PATTERN.search(text):
        return VisualContinuity(inherit=False, reason="explicit_topic_switch", isolation_token=token)
    source = last_visual_turn(turn_records, max_turns=max_turns, exclude_turn_id=exclude_turn_id)
    if source is None:
        return VisualContinuity(inherit=False, reason="no_recent_visual_turn", isolation_token=token)
    return VisualContinuity(
        inherit=True,
        reason="text_followup_inherits_visual",
        source_turn_id=source.get("turn_id"),
        source_blocks=artifact_blocks(source.get("user_message")),
        isolation_token=context_isolation_token(source.get("user_message")),
    )