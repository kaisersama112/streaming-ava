"""Heuristics that tag each turn for strategy-evaluation analysis."""

from __future__ import annotations

from typing import Any

from ava.domain.multimodal import TurnInput
from ava.domain.routing import RouteDecision
from ava.domain.conversation.state import ConversationState
from ava.domain.conversation.strategy import BranchStrategy


def _contains_any(text: str, keywords: tuple[str, ...] | list[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def classify_user_followup_type(
    state: ConversationState,
    turn_input: TurnInput,
    decision: RouteDecision,
    strategy: BranchStrategy | None,
) -> str:
    text = turn_input.normalized_text()
    has_artifacts = bool(turn_input.artifacts)
    last_turn = {}
    for record in reversed(state.turn_records):
        if record.get("turn_status") == "pending":
            continue
        if record.get("decision") or record.get("strategy") or record.get("assistant_text"):
            last_turn = record
            break
    last_decision = dict(last_turn.get("decision") or {})
    last_strategy = dict(last_turn.get("strategy") or {})

    if not text and has_artifacts:
        return "attachment_only"
    if has_artifacts and text:
        return "multimodal_followup"
    if decision.turn_scene == "clarify" or _contains_any(text, ("这个", "那个", "哪种", "详细还是结论")):
        return "clarification_request"
    if _contains_any(text, ("对吗", "是不是", "可以吗", "我这样理解", "确认一下")):
        return "confirmation_check"
    if _contains_any(text, ("错在哪", "为什么错", "订正", "改错")):
        return "error_correction"
    if _contains_any(text, ("下一步", "然后呢", "继续", "后面怎么做", "再来一道")):
        return "continue_same_task"
    if _contains_any(text, ("谢谢", "你好", "哈哈", "在吗", "收到")) and decision.turn_scene == "casual_chat":
        return "social_backchannel"

    if last_decision.get("turn_scene") == decision.turn_scene:
        if last_strategy.get("strategy_id") == (strategy.strategy_id if strategy else ""):
            return "continue_same_strategy"
        return "continue_same_branch"
    return "new_topic"


def build_evaluation_tags(
    state: ConversationState,
    turn_input: TurnInput,
    decision: RouteDecision,
    strategy: BranchStrategy | None,
) -> dict[str, Any]:
    modalities = [artifact.kind for artifact in turn_input.artifacts] or (["text"] if turn_input.normalized_text() else [])
    analysis = dict(getattr(strategy, "analysis", {}) or {}) if strategy is not None else {}
    frame = dict(analysis.get("education_turn_frame") or analysis.get("task_frame") or {})
    continuity = dict(analysis.get("continuity") or {})
    return {
        "branch": decision.turn_scene,
        "session_scene": decision.session_scene,
        "strategy_id": strategy.strategy_id if strategy else "",
        "policy_id": strategy.policy_id if strategy else "",
        "module": strategy.module if strategy else "",
        "subject": strategy.subject if strategy else "",
        "style": strategy.style if strategy else "",
        "render_template": strategy.render_template if strategy else "",
        "delivery_mode": strategy.delivery_mode if strategy else "",
        "ui_mode": strategy.ui_mode if strategy else "",
        "user_followup_type": classify_user_followup_type(state, turn_input, decision, strategy),
        "input_modalities": modalities,
        "has_artifacts": bool(turn_input.artifacts),
        "intent": decision.intent,
        "route_confidence": decision.confidence,
        "education_turn_frame": frame,
        "continuity": continuity,
    }
