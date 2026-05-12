"""Build structured runtime-context messages for router and responder phases."""

from __future__ import annotations

import json
from typing import Any

from ava.domain.conversation import ContextSnapshot
from ava.domain.routing import RouteDecision
from ava.domain.conversation.strategy import BranchStrategy


def _compact_dict(value: dict[str, Any], *, allowed_keys: tuple[str, ...] | None = None) -> dict[str, Any]:
    source = dict(value or {})
    if allowed_keys is not None:
        source = {key: source.get(key) for key in allowed_keys if key in source}
    return {
        str(key): item
        for key, item in source.items()
        if item not in (None, "", [], {}, ())
    }


def _compact_turn_records(snapshot: ContextSnapshot, limit: int = 3) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for record in list(getattr(snapshot, "turn_records", []) or [])[-limit:]:
        decision = _compact_dict(dict(record.get("decision") or {}))
        strategy = dict(record.get("strategy") or {})
        analysis = dict(strategy.get("analysis") or {})
        frame = dict(analysis.get("education_turn_frame") or analysis.get("task_frame") or {})
        items.append(
            {
                "user_text": str(record.get("user_text", "") or "").strip(),
                "assistant_text": str(record.get("assistant_text", "") or "").strip(),
                "decision": decision,
                "strategy_id": str(strategy.get("strategy_id", "") or "").strip(),
                "policy_id": str(strategy.get("policy_id", "") or "").strip(),
                "frame": _compact_dict(
                    frame,
                    allowed_keys=(
                        "primary_scenario",
                        "primary_action",
                        "learning_objects",
                        "object_scope",
                        "object_continuity",
                    ),
                ),
            }
        )
    return items


def _base_runtime_context(snapshot: ContextSnapshot, *, phase: str) -> dict[str, Any]:
    return {
        "schema_version": "runtime_context.v1",
        "phase": phase,
        "session": {
            "session_id": snapshot.session_id,
            "session_scene": snapshot.session_scene,
            "turn_scene": snapshot.turn_scene,
            "context_profile": snapshot.context_profile,
        },
        "input": {
            "user_text": snapshot.user_text,
            "artifacts_count": len(snapshot.artifacts),
            "reference_artifacts_count": len(snapshot.reference_artifacts),
            "reference_artifacts_inherited": bool(snapshot.reference_artifacts_inherited),
        },
        "context": {
            "history_messages_count": len(snapshot.history_messages),
            "recent_turn_records": _compact_turn_records(snapshot),
        },
    }


def build_router_runtime_context(snapshot: ContextSnapshot) -> dict[str, Any]:
    payload = _base_runtime_context(snapshot, phase="router")
    payload["router"] = {
        "must_return_valid_json": True,
        "must_return_plan": True,
        "instructions": {
            "infer_intent_from_current_input_and_recent_history": True,
            "detect_followup_vs_topic_switch": True,
            "do_not_ignore_history_when_user_text_is_short": True,
            "education_plan_must_include": [
                "module",
                "subject",
                "style",
                "policy_id",
                "primary_scenario",
                "primary_action",
                "learning_objects",
                "object_scope",
                "object_continuity",
                "answer_boundary",
            ],
            "non_education_plan_must_include": ["mode"],
        },
        "output_schema": {
            "session_scene": "education|general",
            "turn_scene": "education|general_qa|casual_chat|clarify",
            "intent": "string",
            "confidence": 0.0,
            "should_preserve_teaching_state": True,
            "need_clarification": False,
            "plan": {
                "branch": "education|general_qa|casual_chat|clarify",
                "mode": "fact|reasoned|howto|compare|troubleshoot|visual|confirm|reaction|praise|backchannel|companion|humor|smalltalk|missing_material|focus|missing_reference|answer_mode|scene|subject",
                "module": "solve|check|explain|drill|answer|qa",
                "subject": "math|english|chinese|cs|physics|history|general",
                "style": "direct|explain_careful|hint_only|step_by_step",
                "policy_id": "string",
                "primary_scenario": "practice|lesson|concept|qa|general",
                "primary_action": "string",
                "learning_objects": ["string"],
                "object_scope": "string",
                "object_continuity": "same|new|uncertain",
                "answer_boundary": "hint_first|full_solution|direct_explain|contextual_only|targeted_answer",
                "prompt_overrides": ["string"],
                "plan_reason": "string",
            },
        },
        "router_artifact_brief": _compact_dict(dict(snapshot.router_artifact_brief or {})),
    }
    return payload


def build_responder_runtime_context(
    snapshot: ContextSnapshot,
    strategy: BranchStrategy,
    decision: RouteDecision | None = None,
) -> dict[str, Any]:
    payload = _base_runtime_context(snapshot, phase="responder")
    analysis = dict(getattr(strategy, "analysis", {}) or {})
    frame = dict(analysis.get("education_turn_frame") or analysis.get("task_frame") or {})
    payload["decision"] = (
        decision.model_dump() if decision is not None else {}
    )
    payload["strategy"] = {
        "branch": strategy.branch,
        "strategy_id": strategy.strategy_id,
        "delivery_mode": strategy.delivery_mode,
        "ui_mode": strategy.ui_mode,
        "policy_id": strategy.policy_id,
        "mode": strategy.mode,
        "module": strategy.module,
        "scene": strategy.scene,
        "subject": strategy.subject,
        "style": strategy.style,
        "source": strategy.source,
        "response_contract": dict(strategy.response_contract or {}),
        "speech_policy": dict(strategy.speech_policy or {}),
    }
    payload["teaching"] = {
        "analysis": _compact_dict(
            analysis,
            allowed_keys=(
                "subject",
                "primary_scenario",
                "primary_action",
                "learning_objects",
                "object_scope",
                "object_continuity",
                "answer_boundary",
                "selected_strategy_id",
                "selected_policy_id",
                "selected_strategy_source",
            ),
        ),
        "frame": _compact_dict(frame),
        "router_plan": _compact_dict(dict(snapshot.router_plan or {})),
        "router_artifact_brief": _compact_dict(dict(snapshot.router_artifact_brief or {})),
    }
    return payload


def build_runtime_context_message(payload: dict[str, Any]) -> dict[str, str]:
    return {
        "role": "system",
        "content": (
            "Runtime context (JSON, internal only):\n"
            + json.dumps(payload, ensure_ascii=False)
        ),
    }
