"""Shared reply-generation helpers for CLI and realtime paths.

This module is the execution boundary after a `TurnPlan` has been locked. It
chooses between the optional Agents SDK backend and the direct LLM backend, then
returns final assistant text or streamed tokens to the caller.
"""

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
from ava.multi_turn_context_builder.types import ConversationContext
from ava.llm_model_executor.service import LLMService
from ava.llm_model_executor.types import InferenceCompleted, OutputTextDelta
from ava.llm_model_executor.types import InferenceTask
from ava.domain.multimodal import TurnInput
from ava.router_selector.schema import RouteDecision
from ava.domain.conversation.state import ConversationState
from ava.capabilities.prompt import build_prompt_center
from configs import settings


@dataclass
class ReplyExecutionResult:
    """Normalized result from either direct LLM or Agents SDK execution."""

    assistant_text: str
    backend: str
    debug: dict[str, Any] = field(default_factory=dict)


def _agents_sdk_enabled_for_plan(plan: TurnPlan, *, api_base: str, api_key: str) -> bool:
    """Gate Agents SDK usage by install status, config, branch, and module."""
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


def _has_multimodal_execution_context(context: ConversationContext) -> bool:
    return context.artifacts.has_any


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


def _build_llm_service() -> LLMService:
    return LLMService(prompt_center=build_prompt_center())


def _select_reply_model(default_model: str, plan: TurnPlan) -> str:
    if _messages_have_direct_media(plan.responder_messages):
        return default_model
    return str(settings.openai_config.model or default_model).strip() or default_model


def generate_reply_sync(
    *,
    state: ConversationState,
    turn_input: TurnInput,
    decision: RouteDecision,
    plan: TurnPlan,
    context: ConversationContext,
    api_base: str,
    api_key: str,
    model: str,
    timeout: int,
    current_turn_id: int | None = None,
) -> ReplyExecutionResult:
    """Generate a full reply for non-streaming callers such as CLI paths."""
    use_agents_sdk = _agents_sdk_enabled_for_plan(plan, api_base=api_base, api_key=api_key)
    if use_agents_sdk and not _has_multimodal_execution_context(context):
        try:
            # Agents SDK can propose bounded state patches through tools. Those
            # patches are applied only after a successful run.
            result: AgentsExecutionResult = run_agents_sdk_sync(
                state=state,
                turn_input=turn_input,
                decision=decision,
                plan=plan,
                context=context,
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
        except Exception:
            # Agents are optional. A failure here falls back to the direct LLM
            # path so the user turn can still complete.
            pass

    reply_model = _select_reply_model(model, plan)
    llm_service = _build_llm_service()
    llm_context = llm_service.build_context(
        task=InferenceTask.GENERATE,
        state=state,
        turn_input=turn_input,
        decision=decision,
        plan=plan,
        context=context,
        metadata={
            "api_base": api_base,
            "api_key": api_key,
            "timeout": timeout,
            "model_override": reply_model,
        },
    )
    result = llm_service.generate(llm_context)
    return ReplyExecutionResult(
        assistant_text=result.text,
        backend="llm_chat",
        debug={"llm_response_state": dict(result.metadata or {})},
    )


def stream_reply_with_callbacks(
    *,
    state: ConversationState,
    turn_input: TurnInput,
    decision: RouteDecision,
    plan: TurnPlan,
    context: ConversationContext,
    api_base: str,
    api_key: str,
    model: str,
    timeout: int,
    on_token: Callable[[str], None],
    current_turn_id: int | None = None,
    stop_event=None,
) -> ReplyExecutionResult:
    """Stream a reply and call `on_token` as soon as text is available."""
    use_agents_sdk = _agents_sdk_enabled_for_plan(plan, api_base=api_base, api_key=api_key) and bool(
        getattr(settings.runtime, "agents_sdk_realtime_enabled", False)
    )
    if use_agents_sdk and not _has_multimodal_execution_context(context):
        try:
            # In realtime mode this backend must still honor stop_event so
            # barge-in can cancel the turn promptly.
            result: AgentsExecutionResult = run_agents_sdk_stream(
                state=state,
                turn_input=turn_input,
                decision=decision,
                plan=plan,
                context=context,
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
        except Exception:
            # Preserve realtime responsiveness by falling back to token
            # streaming instead of surfacing the agent error to TTS.
            pass

    text_parts: list[str] = []
    llm_response_state: dict[str, Any] = {}
    reply_model = _select_reply_model(model, plan)
    llm_service = _build_llm_service()
    llm_context = llm_service.build_context(
        task=InferenceTask.GENERATE,
        state=state,
        turn_input=turn_input,
        decision=decision,
        plan=plan,
        current_turn_id=current_turn_id,
        context=context,
        metadata={
            "api_base": api_base,
            "api_key": api_key,
            "timeout": timeout,
            "model_override": reply_model,
        },
    )
    for event in llm_service.stream_generate(
        llm_context,
        stop_event=stop_event,
    ):
        if isinstance(event, OutputTextDelta):
            text_parts.append(event.text)
            on_token(event.text)
        elif isinstance(event, InferenceCompleted):
            llm_response_state = dict(event.metadata or {})
            break
    return ReplyExecutionResult(
        assistant_text="".join(text_parts),
        backend="llm_chat_stream",
        debug={"llm_response_state": llm_response_state},
    )


