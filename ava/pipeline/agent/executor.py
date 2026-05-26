"""Execution helpers that run selected turns through OpenAI Agents SDK.

Agents are an optional execution backend behind the same `TurnPlan` contract as
direct LLM generation. They may call tools and propose small continuity-state
patches, but they should not mutate `ConversationState` directly while a run is
in progress.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable

from agents import RawResponsesStreamEvent, RunItemStreamEvent, Runner
from openai.types.responses import ResponseTextDeltaEvent

from ava.pipeline.generation.types import TurnPlan
from ava.core.tracing import append_trace_log, sanitize_value
from ava.context_engine.types import ContextSnapshot
from ava.domain.multimodal import TurnInput
from ava.domain.routing.schema import RouteDecision
from ava.domain.conversation.state import ConversationState
from configs import settings

from .agents import build_manager_agent, current_user_input
from .context import AvaAgentContext
from .model_factory import AgentsModelConfig, build_agents_sdk_run_config
from .sessions import build_agent_session, seed_agent_session_from_snapshot


@dataclass
class AgentsExecutionResult:
    """Normalized output returned to `reply_service` after an agent run."""

    assistant_text: str
    backend: str = "openai_agents_sdk"
    debug_events: list[dict[str, Any]] = field(default_factory=list)
    applied_patches: list[dict[str, Any]] = field(default_factory=list)


def _apply_pending_state_patches(runtime: AvaAgentContext) -> list[dict[str, Any]]:
    """Apply a guarded subset of tool-requested patches after success only."""
    applied: list[dict[str, Any]] = []
    allowed_education_keys = {"knowledge_point", "stage", "last_problem", "level"}
    for patch in runtime.pending_state_patches:
        key = str(patch.get("key", "") or "").strip()
        value = str(patch.get("value", "") or "").strip()
        reason = str(patch.get("reason", "") or "").strip()
        if not key or not value:
            continue
        if key in allowed_education_keys:
            runtime.state.memory.set_education_state_value(key, value[:160])
            applied.append({"key": key, "value": value[:160], "reason": reason})
    return applied


def _timeout_seconds(timeout: int | None = None) -> int:
    return int(timeout or getattr(settings.runtime, "agents_sdk_timeout", settings.openai_config.timeout) or settings.openai_config.timeout)


def _max_turns() -> int:
    return int(getattr(settings.runtime, "agents_sdk_max_turns", 6) or 6)


def _build_runtime_context(
    *,
    state: ConversationState,
    snapshot: ContextSnapshot,
    decision: RouteDecision,
    plan: TurnPlan,
    turn_input: TurnInput,
    current_turn_id: int | None,
    stop_event=None,
) -> AvaAgentContext:
    """Build local context shared by agent instructions, tools, and callbacks."""
    return AvaAgentContext(
        session_id=state.session_id,
        turn_id=current_turn_id,
        state=state,
        snapshot=snapshot,
        decision=decision,
        strategy=plan.strategy,
        turn_input=turn_input,
        stop_event=stop_event,
    )


def _workflow_name(plan: TurnPlan) -> str:
    return f"AVA Agents SDK {plan.strategy.strategy_id}"


async def _close_model_client(model: object) -> None:
    client = getattr(model, "_client", None)
    if client is None:
        return
    close = getattr(client, "close", None)
    if close is None:
        return
    result = close()
    if asyncio.iscoroutine(result):
        await result


def _build_model_config(
    *,
    api_base: str,
    api_key: str,
    model: str,
    timeout: int,
) -> AgentsModelConfig:
    return AgentsModelConfig(
        api_base=api_base,
        api_key=api_key,
        model=model,
        multimodal_model=model,
        timeout=timeout,
    )


def run_agents_sdk_sync(
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
) -> AgentsExecutionResult:
    """Run the selected plan to completion through the Agents SDK."""
    runtime = _build_runtime_context(
        state=state,
        snapshot=snapshot,
        decision=decision,
        plan=plan,
        turn_input=turn_input,
        current_turn_id=current_turn_id,
    )
    model_config = _build_model_config(
        api_base=api_base,
        api_key=api_key,
        model=model,
        timeout=timeout,
    )
    manager = build_manager_agent(plan, snapshot, model_config=model_config)
    session = build_agent_session(state.session_id)
    run_config = build_agents_sdk_run_config(
        workflow_name=_workflow_name(plan),
        trace_id=f"{state.session_id}:{current_turn_id or 'cli'}",
    )
    payload = current_user_input(plan, turn_input)

    append_trace_log(
        "agents_sdk.run.start",
        {
            "session_id": state.session_id,
            "turn_id": current_turn_id,
            "strategy_id": plan.strategy.strategy_id,
            "backend": "sync",
        },
        turn_id=current_turn_id,
        scope="agents_sdk",
    )

    async def _run() -> Any:
        # Seed the SDK session from the same visible context used by the normal
        # responder path so both backends see comparable recent history.
        await seed_agent_session_from_snapshot(session, snapshot)
        try:
            return await asyncio.wait_for(
                Runner.run(
                    manager,
                    payload,
                    context=runtime,
                    max_turns=_max_turns(),
                    run_config=run_config,
                    session=session,
                ),
                timeout=_timeout_seconds(timeout),
            )
        finally:
            await _close_model_client(manager.model)

    result = asyncio.run(_run())
    assistant_text = str(getattr(result, "final_output", "") or "").strip()
    if not assistant_text:
        assistant_text = str(result.final_output_as(str)).strip()
    if not assistant_text:
        raise RuntimeError("OpenAI Agents SDK returned empty final output.")

    applied_patches = _apply_pending_state_patches(runtime)
    append_trace_log(
        "agents_sdk.run.completed",
        {
            "session_id": state.session_id,
            "turn_id": current_turn_id,
            "strategy_id": plan.strategy.strategy_id,
            "assistant_text": assistant_text,
            "applied_patches": sanitize_value(applied_patches),
            "debug_events": sanitize_value(runtime.debug_events),
        },
        turn_id=current_turn_id,
        scope="agents_sdk",
    )
    return AgentsExecutionResult(
        assistant_text=assistant_text,
        debug_events=runtime.debug_events,
        applied_patches=applied_patches,
    )


def run_agents_sdk_stream(
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
) -> AgentsExecutionResult:
    """Run the selected plan through the Agents SDK and stream text deltas."""
    runtime = _build_runtime_context(
        state=state,
        snapshot=snapshot,
        decision=decision,
        plan=plan,
        turn_input=turn_input,
        current_turn_id=current_turn_id,
        stop_event=stop_event,
    )
    model_config = _build_model_config(
        api_base=api_base,
        api_key=api_key,
        model=model,
        timeout=timeout,
    )
    manager = build_manager_agent(plan, snapshot, model_config=model_config)
    session = build_agent_session(state.session_id)
    run_config = build_agents_sdk_run_config(
        workflow_name=_workflow_name(plan),
        trace_id=f"{state.session_id}:{current_turn_id or 'stream'}",
    )
    payload = current_user_input(plan, turn_input)

    append_trace_log(
        "agents_sdk.stream.start",
        {
            "session_id": state.session_id,
            "turn_id": current_turn_id,
            "strategy_id": plan.strategy.strategy_id,
        },
        turn_id=current_turn_id,
        scope="agents_sdk",
    )

    async def _run() -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
        text_parts: list[str] = []
        await seed_agent_session_from_snapshot(session, snapshot)
        stream = Runner.run_streamed(
            manager,
            payload,
            context=runtime,
            max_turns=_max_turns(),
            run_config=run_config,
            session=session,
        )
        try:
            async for event in stream.stream_events():
                if stop_event is not None and stop_event.is_set():
                    # Realtime barge-in must stop agent streaming quickly; the
                    # caller will persist the turn as interrupted.
                    stream.cancel()
                    runtime.add_event("stream.cancelled", {})
                    break
                if isinstance(event, RawResponsesStreamEvent) and isinstance(event.data, ResponseTextDeltaEvent):
                    delta = str(event.data.delta or "")
                    if delta:
                        text_parts.append(delta)
                        on_token(delta)
                    continue
                if isinstance(event, RunItemStreamEvent):
                    runtime.add_event(
                        f"run_item.{event.name}",
                        {"item_type": type(event.item).__name__},
                    )
            assistant_text = str(getattr(stream, "final_output", "") or "").strip() or "".join(text_parts).strip()
            if not assistant_text:
                raise RuntimeError("OpenAI Agents SDK stream finished without final text.")
            if not text_parts and assistant_text:
                on_token(assistant_text)
            applied_patches = _apply_pending_state_patches(runtime)
            return assistant_text, runtime.debug_events, applied_patches
        finally:
            await _close_model_client(manager.model)

    assistant_text, debug_events, applied_patches = asyncio.run(asyncio.wait_for(_run(), timeout=_timeout_seconds(timeout)))
    append_trace_log(
        "agents_sdk.stream.completed",
        {
            "session_id": state.session_id,
            "turn_id": current_turn_id,
            "strategy_id": plan.strategy.strategy_id,
            "assistant_text": assistant_text,
            "applied_patches": sanitize_value(applied_patches),
            "debug_events": sanitize_value(debug_events),
        },
        turn_id=current_turn_id,
        scope="agents_sdk",
    )
    return AgentsExecutionResult(
        assistant_text=assistant_text,
        debug_events=debug_events,
        applied_patches=applied_patches,
    )

