"""Run the router model directly without a service wrapper.

The router is the first model call in a turn. Its job is deliberately narrow:
classify the current turn, choose the scene/intent, and return a compact `plan`
payload that downstream generation can lock onto. It should not produce user
visible answer text.
"""

from __future__ import annotations

from dataclasses import replace
import json
from typing import Any

from ava.core.context.continuity import (
    select_router_model,
    should_isolate_current_artifact_context,
)
from ava.core.context.snapshot import build_context_snapshot
from ava.capabilities.prompt import (
    build_router_runtime_context,
    build_runtime_context_message,
)
from ava.core.tracing import append_trace_log, sanitize_turn_input, sanitize_value
from ava.domain.conversation import ContextSnapshot
from ava.domain.multimodal import TurnInput
from ava.domain.routing import RouteDecision, apply_confidence_policy
from ava.domain.conversation.state import ConversationState
from ava.capabilities.llm import client as llm_client
from ava.capabilities.prompt import PromptCenter, build_router_system_prompt, build_router_user_message
from configs import settings


def _compact_router_context_trace(context) -> dict[str, Any]:
    return {
        "session_id": getattr(context, "session_id", ""),
        "context_profile": getattr(context, "context_profile", ""),
        "user_text": getattr(context, "user_text", ""),
        "session_scene": getattr(context, "session_scene", ""),
        "turn_scene": getattr(context, "turn_scene", ""),
        "artifacts_count": len(getattr(context, "artifacts", ()) or ()),
        "reference_artifacts_count": len(getattr(context, "reference_artifacts", ()) or ()),
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


def _build_router_messages(
    prompt_center: PromptCenter,
    snapshot: ContextSnapshot,
    *,
    text_only: bool = False,
) -> list[dict[str, object]]:
    """Build the router prompt with the smallest context needed for planning."""
    runtime_context = build_router_runtime_context(snapshot)
    messages: list[dict[str, object]] = [
        {"role": "system", "content": build_router_system_prompt(prompt_center)},
        build_runtime_context_message(runtime_context),
    ]
    if snapshot.history_messages:
        messages.extend(snapshot.history_messages)
    messages.append(
        build_router_user_message(
            snapshot,
            text_only=text_only,
        )
    )
    return messages


def _extract_json_object(text: str) -> dict[str, Any]:
    """Parse a router JSON object even when the model wraps it in prose."""
    text = text.strip()
    if not text:
        raise ValueError("empty router output")

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("json object not found")

    candidate = text[start : end + 1]
    return json.loads(candidate)


def route_with_context(
    *,
    prompt_center: PromptCenter,
    turn_input: TurnInput | str,
    state: ConversationState,
    history_window: int,
    max_context_messages: int | None = None,
    current_turn_id: int | None = None,
    snapshot=None,
    api_base: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
    multimodal_model: str | None = None,
    timeout: int | None = None,
) -> tuple[RouteDecision, Any]:
    """Route one turn and return the normalized decision plus enriched context.

    The returned context carries `router_plan`, which lets generation reuse the
    router's reasoning without asking another planning model. A future long-term
    memory retriever should feed compact, planning-safe facts into the snapshot
    before this function builds messages.
    """
    selected_api_base = api_base or settings.openai_config.api_base
    selected_api_key = api_key or settings.openai_config.api_key
    selected_model_name = model or settings.runtime.router_model or settings.openai_config.model or settings.openai_config.intent_model
    selected_multimodal_model = str(multimodal_model or settings.openai_config.multimodal_model or selected_model_name).strip() or selected_model_name
    selected_timeout = timeout or settings.runtime.router_timeout

    # The router profile intentionally keeps history and multimodal context
    # compact. It is optimized for choosing a path, not answering the user.
    context = snapshot or build_context_snapshot(
        state,
        turn_input,
        history_window,
        current_turn_id=current_turn_id,
        max_context_messages=max_context_messages,
        profile="router",
    )
    # Some fresh artifact uploads should be routed as a new object even when the
    # previous session was in an education flow. This prevents stale continuity
    # memory from forcing the wrong branch.
    isolate_current_artifact_context = should_isolate_current_artifact_context(
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
            history_messages=[],
            turn_records=[],
        )

    # If an upstream artifact brief already summarizes the visual content, the
    # router can often use the text model and avoid re-sending media.
    artifact_brief = dict(getattr(route_context, "router_artifact_brief", {}) or {})
    artifact_brief_source = str(artifact_brief.get("source") or "").strip()
    text_only_router = artifact_brief_source in {"turn_result", "llm_brief"}
    chosen_model = select_router_model(
        route_context,
        text_only=text_only_router,
        model=selected_model_name,
        multimodal_model=selected_multimodal_model,
    )
    append_trace_log(
        "router.route.start",
        {
            "turn_input": sanitize_turn_input(route_context.turn_input),
            "context": _compact_router_context_trace(route_context),
            "model": chosen_model,
            "artifact_brief_source": artifact_brief_source,
            "text_only_router": text_only_router,
            "isolate_current_artifact_context": isolate_current_artifact_context,
            "timeout": selected_timeout,
        },
        turn_id=current_turn_id,
        scope="router",
    )

    messages = _build_router_messages(
        prompt_center,
        route_context,
        text_only=text_only_router,
    )
    append_trace_log(
        "router.route.request",
        {
            "model": selected_model_name,
            "selected_model": chosen_model,
            "artifact_brief": artifact_brief,
            "single_model_plan": True,
            "messages": _compact_router_messages_trace(messages),
        },
        turn_id=current_turn_id,
        scope="router",
    )

    try:
        raw = llm_client.chat(
            api_base=selected_api_base,
            api_key=selected_api_key,
            model=chosen_model,
            messages=messages,
            timeout=selected_timeout,
            temperature=0.1,
            modalities=["text"],
        )
        append_trace_log(
            "router.route.raw_response",
            {"raw": raw},
            turn_id=current_turn_id,
            scope="router",
        )
        obj = _extract_json_object(raw)
        decision_payload = {key: value for key, value in obj.items() if key != "plan"}
        decision = RouteDecision.model_validate(decision_payload)
        final_decision = apply_confidence_policy(decision, current_session_scene=route_context.session_scene)
        plan = dict(obj.get("plan") or {})
        if not plan:
            raise ValueError("Router model response missing required `plan` payload")
        enriched_context = replace(route_context, router_plan=plan)
        selection_summary = {
            "session_id": state.session_id,
            "turn_id": current_turn_id,
            "model": selected_model_name,
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
                "selection_summary": selection_summary,
            },
            turn_id=current_turn_id,
            scope="router",
        )
        print("[router-selection]", json.dumps(selection_summary, ensure_ascii=False))
        return final_decision, enriched_context
    except Exception as exc:
        append_trace_log(
            "router.route.error",
            {
                "error": str(exc),
                "model": chosen_model,
                "artifact_brief_source": artifact_brief_source,
                "text_only_router": text_only_router,
            },
            turn_id=current_turn_id,
            scope="router",
        )
        raise

