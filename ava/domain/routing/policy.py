"""Confidence policy that normalizes router output into safe decisions."""

from __future__ import annotations

from .schema import RouteDecision


def _clarify_decision(current_session_scene: str) -> RouteDecision:
    return RouteDecision(
        session_scene="education" if current_session_scene == "education" else "general",
        turn_scene="clarify",
        intent="clarify",
        confidence=0.49,
        should_preserve_teaching_state=(current_session_scene == "education"),
        need_clarification=True,
    )


def apply_confidence_policy(
    decision: RouteDecision,
    current_session_scene: str,
) -> RouteDecision:
    if decision.turn_scene == "education":
        decision.session_scene = "education"
        decision.should_preserve_teaching_state = True
    if decision.turn_scene == "clarify":
        decision.need_clarification = True

    if decision.confidence < 0.5:
        return _clarify_decision(current_session_scene)

    if decision.confidence < 0.8:
        if current_session_scene == "education" and decision.turn_scene in {"general_qa", "casual_chat"}:
            decision.session_scene = "education"
            decision.should_preserve_teaching_state = True
            return decision
        if current_session_scene != decision.session_scene:
            return _clarify_decision(current_session_scene)

    return decision
