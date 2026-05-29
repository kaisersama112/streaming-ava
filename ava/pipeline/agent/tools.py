"""Function tools exposed to Agents SDK managers and specialists."""

from __future__ import annotations

import json
from typing import Any

from agents import RunContextWrapper, function_tool

from .context import AvaAgentContext


def _safe_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


@function_tool
def get_turn_plan(context: RunContextWrapper[AvaAgentContext]) -> str:
    """Return the locked route decision and execution strategy for the current turn."""
    runtime = context.context
    payload = {
        "session_scene": runtime.decision.session_scene,
        "turn_scene": runtime.decision.turn_scene,
        "intent": runtime.decision.intent,
        "need_clarification": runtime.decision.need_clarification,
        "should_preserve_teaching_state": runtime.decision.should_preserve_teaching_state,
        "strategy_id": runtime.strategy.strategy_id,
        "branch": runtime.strategy.branch,
        "mode": runtime.strategy.mode,
        "module": runtime.strategy.module,
        "subject": runtime.strategy.subject,
        "pedagogy": runtime.strategy.pedagogy,
        "policy_id": runtime.strategy.policy_id,
        "analysis": dict(runtime.strategy.analysis or {}),
    }
    runtime.add_event("tool.get_turn_plan", {"strategy_id": runtime.strategy.strategy_id})
    return _safe_json(payload)


@function_tool
def get_recent_history(context: RunContextWrapper[AvaAgentContext], limit: int = 8) -> str:
    """Return recent user and assistant turns that matter for the current turn."""
    runtime = context.context
    window = max(2, min(int(limit or 8), 12))
    history = runtime.context.conversation[-window:]
    runtime.add_event("tool.get_recent_history", {"limit": window, "items": len(history)})
    return _safe_json(history)


@function_tool
def get_reference_materials(context: RunContextWrapper[AvaAgentContext]) -> str:
    """Return a compact summary of current and inherited multimodal materials."""
    runtime = context.context
    payload = {
        "current_artifacts": [artifact.to_prompt_dict() for artifact in runtime.context.artifacts.current],
        "reference_artifacts": [artifact.to_prompt_dict() for artifact in runtime.context.artifacts.reference],
        "input_summary": runtime.turn_input.multimodal_summary() or runtime.context.current.user_text,
    }
    runtime.add_event(
        "tool.get_reference_materials",
        {
            "current_artifacts": len(runtime.context.artifacts.current),
            "reference_artifacts": len(runtime.context.artifacts.reference),
        },
    )
    return _safe_json(payload)


@function_tool
def note_state_patch(
    context: RunContextWrapper[AvaAgentContext],
    key: str,
    value: str,
    reason: str,
) -> str:
    """Request a lightweight continuity-state patch to be applied after the run succeeds."""
    runtime = context.context
    runtime.add_patch(key=key, value=value, reason=reason)
    runtime.add_event(
        "tool.note_state_patch",
        {"key": str(key or "").strip(), "reason": str(reason or "").strip()},
    )
    return "已记录建议的状态补丁，最终是否应用由运行时决定。"
