"""为单轮生成轻量评估标签。"""

from __future__ import annotations

from typing import Any

from ava.domain.conversation.state import ConversationState
from ava.domain.conversation.strategy import BranchStrategy
from ava.router_selector.schema import RouteDecision


def _contains_any(text: str, keywords: tuple[str, ...] | list[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def _prompt_profile_from_strategy(strategy: BranchStrategy | None) -> dict[str, Any]:
    if strategy is None:
        return {}
    return dict(strategy.prompt_profile())


def classify_user_followup_type(
    state: ConversationState,
    user_message: dict[str, Any],
    decision: RouteDecision,
    strategy: BranchStrategy | None,
) -> str:
    text_blocks = [
        str(block.get("text", "") or "").strip()
        for block in list(user_message.get("content") or [])
        if isinstance(block, dict) and str(block.get("type", "") or "").strip() == "input_text"
    ]
    text = "\n".join(item for item in text_blocks if item)
    has_artifacts = any(
        isinstance(block, dict) and str(block.get("type", "") or "").strip() != "input_text"
        for block in list(user_message.get("content") or [])
    )
    last_turn = {}
    for record in reversed(state.turn_records):
        if record.get("turn_status") == "pending":
            continue
        assistant_message = dict(record.get("assistant_message") or {})
        has_assistant_output_text = any(
            isinstance(block, dict)
            and str(block.get("type", "") or "").strip() == "output_text"
            and str(block.get("text", "") or "").strip()
            for block in list(assistant_message.get("content") or [])
        )
        if record.get("decision") or record.get("strategy") or has_assistant_output_text:
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
    user_message: dict[str, Any],
    decision: RouteDecision,
    strategy: BranchStrategy | None,
) -> dict[str, Any]:
    modalities = [
        str(block.get("type", "") or "").strip().replace("input_", "")
        for block in list(user_message.get("content") or [])
        if isinstance(block, dict) and str(block.get("type", "") or "").strip() != "input_text"
    ] or (["text"] if any(
        isinstance(block, dict)
        and str(block.get("type", "") or "").strip() == "input_text"
        and str(block.get("text", "") or "").strip()
        for block in list(user_message.get("content") or [])
    ) else [])
    analysis = dict(getattr(strategy, "analysis", {}) or {}) if strategy is not None else {}
    frame = dict(analysis.get("education_turn_frame") or analysis.get("task_frame") or {})
    continuity = dict(analysis.get("continuity") or {})
    prompt_profile = _prompt_profile_from_strategy(strategy)
    return {
        "turn_scene": decision.turn_scene,
        "session_scene": decision.session_scene,
        "capability": prompt_profile.get("capability", ""),
        "task": prompt_profile.get("task", ""),
        "knowledge": prompt_profile.get("knowledge", ""),
        "method": prompt_profile.get("method", ""),
        "audience": prompt_profile.get("audience", ""),
        "skills": list(prompt_profile.get("skills") or []),
        "prompt_source": strategy.source if strategy else "",
        "user_followup_type": classify_user_followup_type(state, user_message, decision, strategy),
        "input_modalities": modalities,
        "has_artifacts": bool(modalities and modalities != ["text"]),
        "intent": decision.intent,
        "route_confidence": decision.confidence,
        "education_turn_frame": frame,
        "continuity": continuity,
    }
