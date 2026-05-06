"""Router LLM service that converts user input into a route decision."""

from __future__ import annotations

from dataclasses import replace
import json
from typing import Any

from ava.domain.context import assemble_context
from ava.domain.context import TurnInput
from ava.domain.routing import RouteDecision, apply_confidence_policy
from ava.domain.session.state import ConversationState
from ava.application.trace import append_trace_log, sanitize_turn_input, sanitize_value
from ava.infrastructure.llm import client as llm_client

from .heuristics import heuristic_route
from .parser import extract_json_object
from .multimodal import build_router_messages
from ava.infrastructure.prompts import PromptCenter

_CURRENT_ARTIFACT_STRONG_CONTINUITY_CUES = (
    "上一题",
    "上题",
    "继续",
    "接着",
    "我圈出来了",
    "我改了",
    "我这样做",
    "我写了",
    "做对了吗",
    "对不对",
    "算对了吗",
    "写对了吗",
    "为什么不是",
    "为什么要",
    "哪一步",
    "错在哪",
    "哪错了",
)


def _compact_router_context_trace(context) -> dict[str, Any]:
    return {
        "session_id": getattr(context, "session_id", ""),
        "context_profile": getattr(context, "context_profile", ""),
        "user_text": getattr(context, "user_text", ""),
        "session_scene": getattr(context, "session_scene", ""),
        "turn_scene": getattr(context, "turn_scene", ""),
        "artifacts_count": len(getattr(context, "artifacts", ()) or ()),
        "reference_artifacts_count": len(getattr(context, "reference_artifacts", ()) or ()),
        "recent_history_summary_len": len(str(getattr(context, "recent_history_summary", "") or "")),
        "recent_turns_summary_len": len(str(getattr(context, "recent_turns_summary", "") or "")),
    }


def _compact_router_messages_trace(messages: list[dict[str, Any]]) -> dict[str, Any]:
    if not messages:
        return {"count": 0}
    return {
        "count": len(messages),
        "roles": [str(item.get("role", "")).strip() for item in messages],
        "first_message_preview": sanitize_value(messages[0].get("content", ""), text_limit=400),
        "last_message_preview": sanitize_value(messages[-1].get("content", ""), text_limit=400),
    }


def _should_isolate_current_artifact_context(
    state: ConversationState,
    context,
    *,
    current_turn_id: int | None = None,
) -> bool:
    current_artifacts = tuple(getattr(context, "artifacts", ()) or ())
    if not current_artifacts:
        return False

    previous_artifacts = state.recent_reference_artifacts(
        current_turn_id=current_turn_id,
        limit_turns=1,
    )
    if not previous_artifacts:
        return True

    current_key = state.artifact_bundle_key(current_artifacts)
    previous_key = state.artifact_bundle_key(previous_artifacts)
    if current_key and current_key == previous_key:
        return False

    text = str(getattr(context, "user_text", "") or "").strip().lower()
    if not text:
        return True

    return not any(token in text for token in _CURRENT_ARTIFACT_STRONG_CONTINUITY_CUES)


def _normalize_subject(value: str) -> str:
    normalized = str(value or "").strip()
    mapping = {
        "数学": "math",
        "英语": "english",
        "语文": "chinese",
        "计算机": "cs",
        "编程": "cs",
        "物理": "physics",
        "历史": "history",
    }
    normalized = mapping.get(normalized, normalized.lower())
    if normalized in {"math", "english", "chinese", "cs", "physics", "history", "general"}:
        return normalized
    return "general"


def _fallback_router_plan(decision: RouteDecision, context, state: ConversationState) -> dict[str, Any]:
    text = str(getattr(context, "user_text", "") or "").strip()
    lower_text = text.lower()

    if decision.turn_scene == "education":
        education_state = dict(getattr(state, "education_state", {}) or {})
        subject = _normalize_subject(str(education_state.get("subject") or ""))
        primary_action = str(education_state.get("primary_action") or "").strip()
        primary_scenario = str(education_state.get("learning_scenario") or "").strip() or "practice"
        learning_objects = list(education_state.get("learning_objects") or []) or ["problem"]
        object_scope = str(education_state.get("object_scope") or "").strip() or "whole_problem"
        object_continuity = str(education_state.get("object_continuity") or "").strip() or "uncertain"

        if any(token in text for token in ("不会", "没懂", "不懂", "卡住", "下一步", "继续", "然后呢")):
            primary_action = primary_action or "diagnose_error"
            object_scope = "knowledge_gap"
            learning_objects = ["knowledge_gap"]
        elif any(token in text for token in ("对吗", "对不对", "做对了吗", "答对了吗", "算对了吗", "写对了吗")):
            primary_action = primary_action or "check_solution"
            learning_objects = ["student_solution"]
            object_scope = "student_solution"
        else:
            primary_action = primary_action or "solve_current_problem"

        module = "solve"
        style = "hint_only"
        policy_id = "practice.guided_solving"
        answer_boundary = "hint_first"
        if primary_action in {"diagnose_error", "explain_concept", "summarize_concept", "explain_local_step"}:
            module = "explain"
            style = "explain_careful"
            policy_id = "practice.error_diagnosis" if primary_action == "diagnose_error" else "concept.intuition_first"
            answer_boundary = "direct_explain"
        elif primary_action == "check_solution":
            module = "check"
            style = "direct"
            policy_id = "practice.solution_check"
            answer_boundary = "direct_explain"
        elif primary_action == "generate_exercise_set":
            module = "drill"
            style = "direct"
            policy_id = "practice.exercise_generation"
            answer_boundary = "targeted_answer"

        return {
            "branch": "education",
            "module": module,
            "subject": subject,
            "style": style,
            "policy_id": policy_id,
            "primary_scenario": primary_scenario,
            "primary_action": primary_action,
            "learning_objects": learning_objects,
            "object_scope": object_scope,
            "object_continuity": object_continuity,
            "answer_boundary": answer_boundary,
            "prompt_overrides": [],
            "plan_reason": "router_fallback",
        }

    if decision.turn_scene == "general_qa":
        mode = "fact"
        if any(token in text for token in ("为什么", "为何", "原因")):
            mode = "reasoned"
        elif any(token in text for token in ("怎么", "如何", "步骤", "设置", "安装", "连接")):
            mode = "howto"
        elif any(token in text for token in ("区别", "哪个好", "怎么选", "对比", "差别")):
            mode = "compare"
        elif any(token in text for token in ("打不开", "报错", "失败", "不能用", "没反应")):
            mode = "troubleshoot"
        elif any(token in text for token in ("对吗", "是不是", "可以吗", "这样行吗")):
            mode = "confirm"
        return {"branch": "general_qa", "mode": mode, "plan_reason": "router_fallback"}

    if decision.turn_scene == "casual_chat":
        mode = "smalltalk"
        if any(token in text for token in ("谢谢", "真厉害", "太棒了", "不错")):
            mode = "praise"
        elif any(token in text for token in ("哈哈", "笑死", "好玩")):
            mode = "humor"
        elif lower_text in {"嗯", "好", "好的", "行", "ok"}:
            mode = "backchannel"
        elif any(token in text for token in ("累", "烦", "难受", "不想学")):
            mode = "companion"
        return {"branch": "casual_chat", "mode": mode, "plan_reason": "router_fallback"}

    mode = "subject"
    if not getattr(context, "artifacts", ()) and any(token in text for token in ("这道题", "这张图", "这个视频", "这段音频")):
        mode = "missing_material"
    elif any(token in text for token in ("这个", "那个", "这里", "那里")):
        mode = "missing_reference"
    elif any(token in text for token in ("讲一下", "说说", "解释")):
        mode = "answer_mode"
    return {"branch": "clarify", "mode": mode, "plan_reason": "router_fallback"}


class RouterService:
    """Coordinates prompt assembly, router inference, and fallback policy."""

    def __init__(
            self,
            api_base: str,
            api_key: str,
            model: str,
            multimodal_model: str | None,
            timeout: int,
            prompt_center: PromptCenter,
    ):
        self.api_base = api_base
        self.api_key = api_key
        self.model = model
        self.multimodal_model = str(multimodal_model or "").strip() or model
        self.timeout = timeout
        self.prompt_center = prompt_center

    def _select_model_for_context(self, context, *, text_only: bool = False) -> str:
        if text_only:
            return self.model
        if getattr(context, "artifacts", ()) or getattr(context, "reference_artifacts", ()):
            return self.multimodal_model
        return self.model

    def route(
            self,
            turn_input: TurnInput | str,
            state: ConversationState,
            history_window: int,
            max_context_messages: int | None = None,
            current_turn_id: int | None = None,
            snapshot=None,
    ) -> RouteDecision:
        decision, _ = self.route_with_context(
            turn_input,
            state,
            history_window,
            max_context_messages=max_context_messages,
            current_turn_id=current_turn_id,
            snapshot=snapshot,
        )
        return decision

    def route_with_context(
            self,
            turn_input: TurnInput | str,
            state: ConversationState,
            history_window: int,
            max_context_messages: int | None = None,
            current_turn_id: int | None = None,
            snapshot=None,
    ) -> tuple[RouteDecision, Any]:
        """Return a validated route decision for the current user turn."""
        context = snapshot or assemble_context(
            state,
            turn_input,
            history_window,
            current_turn_id=current_turn_id,
            max_context_messages=max_context_messages,
            profile="router",
        )
        isolate_current_artifact_context = _should_isolate_current_artifact_context(
            state,
            context,
            current_turn_id=current_turn_id,
        )
        route_context = context
        if isolate_current_artifact_context:
            route_context = replace(
                context,
                session_scene="general",
                turn_scene="general_qa",
                recent_history_summary="",
                recent_turns_summary="",
                history_messages=[],
                education_state={},
                turn_records=[],
            )
        fallback = apply_confidence_policy(
            heuristic_route(route_context.user_text, route_context.session_scene),
            current_session_scene=route_context.session_scene,
        )
        artifact_brief = dict(getattr(route_context, "router_artifact_brief", {}) or {})
        artifact_brief_source = str(artifact_brief.get("source") or "").strip()
        text_only_router = artifact_brief_source in {"turn_result", "llm_brief"}
        selected_model = self._select_model_for_context(route_context, text_only=text_only_router)
        append_trace_log(
            "router.route.start",
            {
                "turn_input": sanitize_turn_input(route_context.turn_input),
                "context": _compact_router_context_trace(route_context),
                "fallback": sanitize_value(fallback),
                "model": selected_model,
                "artifact_brief_source": artifact_brief_source,
                "text_only_router": text_only_router,
                "isolate_current_artifact_context": isolate_current_artifact_context,
                "timeout": self.timeout,
            },
            turn_id=current_turn_id,
            scope="router",
        )

        messages = build_router_messages(
            self.prompt_center,
            route_context,
            text_only=text_only_router,
            artifact_brief=artifact_brief or None,
        )
        append_trace_log(
            "router.route.request",
            {
                "model": self.model,
                "selected_model": selected_model,
                "artifact_brief": artifact_brief,
                "single_model_plan": True,
                "messages": _compact_router_messages_trace(messages),
            },
            turn_id=current_turn_id,
            scope="router",
        )

        try:
            raw = llm_client.chat(
                api_base=self.api_base,
                api_key=self.api_key,
                model=selected_model,
                messages=messages,
                timeout=self.timeout,
                temperature=0.1,
                modalities=["text"],
            )
            append_trace_log(
                "router.route.raw_response",
                {"raw": raw},
                turn_id=current_turn_id,
                scope="router",
            )
            obj = extract_json_object(raw)
            decision_payload = {key: value for key, value in obj.items() if key != "plan"}
            decision = RouteDecision.model_validate(decision_payload)
            final_decision = apply_confidence_policy(decision, current_session_scene=route_context.session_scene)
            plan = dict(obj.get("plan") or {}) or _fallback_router_plan(final_decision, route_context, state)
            enriched_context = replace(route_context, router_plan=plan)
            selection_summary = {
                "session_id": state.session_id,
                "turn_id": current_turn_id,
                "model": self.model,
                "session_scene": final_decision.session_scene,
                "turn_scene": final_decision.turn_scene,
                "intent": final_decision.intent,
                "confidence": final_decision.confidence,
                "need_clarification": final_decision.need_clarification,
                "should_preserve_teaching_state": final_decision.should_preserve_teaching_state,
                "router_plan": sanitize_value(plan),
            }
            append_trace_log(
                "router.route.decision",
                {
                    "decision": sanitize_value(final_decision),
                    "router_plan": sanitize_value(plan),
                    "fallback": sanitize_value(fallback),
                    "selection_summary": selection_summary,
                },
                turn_id=current_turn_id,
                scope="router",
            )
            print("[router-selection]", json.dumps(selection_summary, ensure_ascii=False))
            return final_decision, enriched_context
        except Exception as exc:
            final_decision = fallback
            fallback_plan = _fallback_router_plan(final_decision, route_context, state)
            fallback_context = replace(route_context, router_plan=fallback_plan)
            selection_summary = {
                "session_id": state.session_id,
                "turn_id": current_turn_id,
                "model": self.model,
                "session_scene": final_decision.session_scene,
                "turn_scene": final_decision.turn_scene,
                "intent": final_decision.intent,
                "confidence": final_decision.confidence,
                "need_clarification": final_decision.need_clarification,
                "should_preserve_teaching_state": final_decision.should_preserve_teaching_state,
                "router_plan": sanitize_value(fallback_plan),
            }
            append_trace_log(
                "router.route.fallback",
                {
                    "error": str(exc),
                    "fallback": sanitize_value(fallback),
                    "router_plan": sanitize_value(fallback_plan),
                    "selection_summary": selection_summary,
                },
                turn_id=current_turn_id,
                scope="router",
            )
            print("[router-selection]", json.dumps(selection_summary, ensure_ascii=False))
            return final_decision, fallback_context
