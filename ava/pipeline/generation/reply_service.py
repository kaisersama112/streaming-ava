"""Shared reply-generation helpers for CLI and realtime paths."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

try:
    from ava.pipeline.agent import AgentsExecutionResult, run_agents_sdk_stream, run_agents_sdk_sync
    _AGENTS_SDK_AVAILABLE = True
except Exception:
    AgentsExecutionResult = Any  # type: ignore[assignment]
    run_agents_sdk_stream = None  # type: ignore[assignment]
    run_agents_sdk_sync = None  # type: ignore[assignment]
    _AGENTS_SDK_AVAILABLE = False
from ava.pipeline.generation.types import TurnPlan
from ava.core.tracing import append_trace_log
from ava.domain.conversation import ContextSnapshot
from ava.domain.multimodal import TurnInput
from ava.domain.routing import RouteDecision
from ava.domain.conversation.state import ConversationState
from ava.capabilities.llm import client as llm_client
from configs import settings


@dataclass
class ReplyExecutionResult:
    assistant_text: str
    backend: str
    debug: dict[str, Any] = field(default_factory=dict)


def _agents_sdk_enabled_for_plan(plan: TurnPlan, *, api_base: str, api_key: str) -> bool:
    if not _AGENTS_SDK_AVAILABLE:
        return False
    if not bool(getattr(settings.runtime, "agents_sdk_enabled", False)):
        return False
    if not str(api_key or "").strip() or not str(api_base or "").strip():
        return False

    allowed_branches = {
        str(item).strip()
        for item in (getattr(settings.runtime, "agents_sdk_branches", []) or [])
        if str(item).strip()
    }
    if allowed_branches and plan.strategy.branch not in allowed_branches:
        return False

    if plan.strategy.branch == "education":
        allowed_modules = {
            str(item).strip()
            for item in (getattr(settings.runtime, "agents_sdk_education_modules", []) or [])
            if str(item).strip()
        }
        if allowed_modules and plan.strategy.module not in allowed_modules:
            return False

    return True


def _has_multimodal_execution_context(snapshot: ContextSnapshot) -> bool:
    return bool(snapshot.artifacts or snapshot.reference_artifacts)


def _messages_have_direct_media(messages: list[dict[str, object]]) -> bool:
    media_types = {"image_url", "input_image", "input_audio", "video", "audio"}
    for message in messages:
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if str(block.get("type", "")).strip() in media_types:
                return True
    return False


def _select_reply_model(default_model: str, plan: TurnPlan) -> str:
    if _messages_have_direct_media(plan.responder_messages):
        return default_model
    return str(settings.openai_config.model or default_model).strip() or default_model


def _append_multimodal_bypass_trace(
    *,
    current_turn_id: int | None,
    strategy_id: str,
    snapshot: ContextSnapshot,
    scope: str,
) -> None:
    append_trace_log(
        scope,
        {
            "turn_id": current_turn_id,
            "strategy_id": strategy_id,
            "reason": "multimodal_context",
            "artifacts_count": len(snapshot.artifacts),
            "reference_artifacts_count": len(snapshot.reference_artifacts),
        },
        turn_id=current_turn_id,
        scope="agents_sdk",
    )


def generate_reply_sync(
    *,
    state: ConversationState,
    turn_input: TurnInput,
    decision: RouteDecision,
    plan: TurnPlan,
    snapshot: ContextSnapshot,
    api_base: str,
    api_key: str,
    model: str,
    timeout: int,
    current_turn_id: int | None = None,
) -> ReplyExecutionResult:
    use_agents_sdk = _agents_sdk_enabled_for_plan(plan, api_base=api_base, api_key=api_key)
    if use_agents_sdk and _has_multimodal_execution_context(snapshot):
        _append_multimodal_bypass_trace(
            current_turn_id=current_turn_id,
            strategy_id=plan.strategy.strategy_id,
            snapshot=snapshot,
            scope="agents_sdk.run.skipped",
        )
    if use_agents_sdk and not _has_multimodal_execution_context(snapshot):
        try:
            result: AgentsExecutionResult = run_agents_sdk_sync(
                state=state,
                turn_input=turn_input,
                decision=decision,
                plan=plan,
                snapshot=snapshot,
                api_base=api_base,
                api_key=api_key,
                model=model,
                timeout=timeout,
                current_turn_id=current_turn_id,
            )
            return ReplyExecutionResult(
                assistant_text=result.assistant_text,
                backend=result.backend,
                debug={
                    "agents_sdk_events": result.debug_events,
                    "agents_sdk_patches": result.applied_patches,
                },
            )
        except Exception as exc:
            append_trace_log(
                "agents_sdk.run.fallback",
                {
                    "turn_id": current_turn_id,
                    "strategy_id": plan.strategy.strategy_id,
                    "error": str(exc),
                },
                turn_id=current_turn_id,
                scope="agents_sdk",
            )

    reply_model = _select_reply_model(model, plan)
    reply = llm_client.chat(
        api_base=api_base,
        api_key=api_key,
        model=reply_model,
        messages=plan.responder_messages,
        timeout=timeout,
        temperature=0.7,
        modalities=["text"],
    )
    return ReplyExecutionResult(assistant_text=reply, backend="llm_chat")


def stream_reply_with_callbacks(
    *,
    state: ConversationState,
    turn_input: TurnInput,
    decision: RouteDecision,
    plan: TurnPlan,
    snapshot: ContextSnapshot,
    api_base: str,
    api_key: str,
    model: str,
    timeout: int,
    on_token: Callable[[str], None],
    current_turn_id: int | None = None,
    stop_event=None,
) -> ReplyExecutionResult:
    use_agents_sdk = _agents_sdk_enabled_for_plan(plan, api_base=api_base, api_key=api_key) and bool(
        getattr(settings.runtime, "agents_sdk_realtime_enabled", False)
    )
    if use_agents_sdk and _has_multimodal_execution_context(snapshot):
        _append_multimodal_bypass_trace(
            current_turn_id=current_turn_id,
            strategy_id=plan.strategy.strategy_id,
            snapshot=snapshot,
            scope="agents_sdk.stream.skipped",
        )
    if use_agents_sdk and not _has_multimodal_execution_context(snapshot):
        try:
            result: AgentsExecutionResult = run_agents_sdk_stream(
                state=state,
                turn_input=turn_input,
                decision=decision,
                plan=plan,
                snapshot=snapshot,
                api_base=api_base,
                api_key=api_key,
                model=model,
                timeout=timeout,
                on_token=on_token,
                current_turn_id=current_turn_id,
                stop_event=stop_event,
            )
            return ReplyExecutionResult(
                assistant_text=result.assistant_text,
                backend=result.backend,
                debug={
                    "agents_sdk_events": result.debug_events,
                    "agents_sdk_patches": result.applied_patches,
                },
            )
        except Exception as exc:
            append_trace_log(
                "agents_sdk.stream.fallback",
                {
                    "turn_id": current_turn_id,
                    "strategy_id": plan.strategy.strategy_id,
                    "error": str(exc),
                },
                turn_id=current_turn_id,
                scope="agents_sdk",
            )

    text_parts: list[str] = []
    reply_model = _select_reply_model(model, plan)
    for token in llm_client.chat_stream(
        api_base=api_base,
        api_key=api_key,
        model=reply_model,
        messages=plan.responder_messages,
        timeout=timeout,
        temperature=0.7,
        modalities=["text"],
        stream_options={"include_usage": True},
        stop_event=stop_event,
    ):
        text_parts.append(token)
        on_token(token)
    return ReplyExecutionResult(
        assistant_text="".join(text_parts),
        backend="llm_chat_stream",
    )


