"""developer runtime 层：运行时状态与记忆投影注入。

把 SessionMemory / ConversationState 中已沉淀的事实（教育态、用户事实槽位、
近期主题、摘要、附件分析缓存、视觉连续性）编译为模型可见的只读运行时上下文。
"""

from __future__ import annotations

import json
from typing import Any

from ava.domain.conversation.state import ConversationState
from ava.domain.multimodal.continuity import (
    artifact_blocks,
    blocks_to_artifacts,
    should_inherit_visual_context,
)
from configs import settings

from .types import ConversationContext

_RUNTIME_SECTION_HEADER = "【运行时状态（只读事实，禁止改写；回答时按需引用）】"
_MAX_SECTION_CHARS = 2600


def build_runtime_payload(
    *,
    state: ConversationState,
    context: ConversationContext,
    profile: str,
    decision: Any | None = None,
    strategy: Any | None = None,
) -> dict[str, Any]:
    """构建当前阶段可见的运行时状态投影。"""
    memory = state.memory
    current_message = context.current.user_message
    current_artifacts = blocks_to_artifacts(artifact_blocks(current_message))
    if current_artifacts:
        analysis = memory.cached_or_metadata_block_analysis(current_artifacts)
        memory.remember_block_analysis(current_artifacts, analysis)

    continuity = should_inherit_visual_context(
        current_message,
        state.turn_records,
        max_turns=int(getattr(settings.runtime, "visual_continuity_max_turns", 2) or 2),
    )
    reference_artifacts = blocks_to_artifacts(continuity.source_blocks or []) if continuity.inherit else []
    if reference_artifacts:
        memory.remember_block_analysis(
            reference_artifacts,
            memory.cached_or_metadata_block_analysis(reference_artifacts),
        )

    projection = memory.build_projection(
        current_message,
        profile=profile,
        current_message_blocks=current_artifacts,
        reference_message_blocks=reference_artifacts,
    )

    payload: dict[str, Any] = {
        "profile": profile,
        "session_scene": context.session.session_scene,
        "turn_scene": context.session.turn_scene,
        "education_state": projection.education_state,
        "user_facts": dict(memory.user_facts),
        "recent_topics": projection.recent_topics,
        "message_block_memory": projection.message_block_memory,
        "retrieved_memories": projection.retrieved_memories,
        "visual_continuity": {
            "inherit": continuity.inherit,
            "reason": continuity.reason,
            "source_turn_id": continuity.source_turn_id,
            "isolation_token": continuity.isolation_token,
        },
    }
    if decision is not None:
        payload["route"] = {
            "intent": str(getattr(decision, "intent", "") or ""),
            "confidence": float(getattr(decision, "confidence", 0.0) or 0.0),
            "need_clarification": bool(getattr(decision, "need_clarification", False)),
        }
    if profile != "router":
        payload["context_summary"] = projection.context_summary
        if current_artifacts or continuity.inherit:
            payload["multimodal_context_summary"] = projection.multimodal_context_summary
        analysis = dict(getattr(strategy, "analysis", {}) or {})
        continuity_hints = dict(analysis.get("continuity") or {})
        if continuity_hints:
            payload["continuity_hints"] = {
                key: continuity_hints[key]
                for key in (
                    "current_turn_is_followup",
                    "current_object_continues",
                    "explicit_topic_switch",
                    "answer_boundary",
                    "previous_answer_boundary",
                )
                if key in continuity_hints
            }
    return {key: value for key, value in payload.items() if value not in (None, "", [], {})}


def render_runtime_section(payload: dict[str, Any]) -> str:
    """把运行时投影渲染为紧凑文本段（注入 instructions 的 developer 层）。"""
    if not payload:
        return ""
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if len(text) > _MAX_SECTION_CHARS:
        text = text[:_MAX_SECTION_CHARS].rstrip() + "…(截断)"
    return f"{_RUNTIME_SECTION_HEADER}\n{text}"