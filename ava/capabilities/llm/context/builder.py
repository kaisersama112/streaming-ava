from dataclasses import replace
from typing import Any

from ava.core.context.continuity import (
    build_artifact_brief_for_context,
    select_router_model,
    should_inherit_reference_artifacts,
    should_isolate_current_artifact_context,
)
from ava.core.context.input import build_turn_input
from ava.domain.conversation.state import ConversationState
from ava.domain.multimodal import TurnInput
from configs import settings

from ava.capabilities.llm.context.history import build_visible_history
from ava.capabilities.llm.context.memory import build_memory_projection
from ava.capabilities.llm.context.multimodal import build_multimodal_projection
from ava.capabilities.llm.context.types import InferenceVisibleContext
from ava.capabilities.llm.types import InferenceTask, LLMContext


def _build_visible_context(
    state: ConversationState,
    turn_input: TurnInput,
    *,
    history_window: int,
    current_turn_id: int | None,
    max_context_messages: int,
    profile: str,
    previous_visible_context: InferenceVisibleContext | None = None,
) -> InferenceVisibleContext:
    max_messages = max(2, int(max_context_messages or (history_window * 2)))
    if current_turn_id is None:
        turn_records = state.turn_records[-max_messages:]
    else:
        turn_records = [item for item in state.turn_records if item.get("turn_id") != current_turn_id][-max_messages:]

    history_messages = build_visible_history(turn_records, max_messages=max_messages)
    user_text = turn_input.normalized_text() or turn_input.multimodal_summary()
    allow_reference_artifacts = should_inherit_reference_artifacts(state, turn_input)
    reference_artifacts = ()
    if allow_reference_artifacts and not turn_input.artifacts:
        reference_artifacts = state.recent_reference_artifacts(current_turn_id=current_turn_id, limit_turns=1)
    artifact_brief = build_artifact_brief_for_context(
        state,
        current_artifacts=turn_input.artifacts,
        reference_artifacts=reference_artifacts,
    )
    visible_context = InferenceVisibleContext(
        turn_input=turn_input,
        user_text=user_text,
        session_id=state.session_id,
        session_scene=state.session_scene,
        turn_scene=state.turn_scene,
        history_messages=history_messages,
        artifacts=turn_input.artifacts,
        reference_artifacts=reference_artifacts,
        turn_records=turn_records,
        context_profile=profile,
        reference_artifacts_inherited=bool(reference_artifacts),
        router_artifact_brief=artifact_brief,
        router_plan={},
    )
    if previous_visible_context is not None:
        visible_context = replace(
            visible_context,
            router_artifact_brief=dict(getattr(previous_visible_context, "router_artifact_brief", {}) or {}),
            router_plan=dict(getattr(previous_visible_context, "router_plan", {}) or {}),
        )
    return visible_context


def build_llm_context(
    *,
    task: InferenceTask,
    state: ConversationState,
    turn_input: TurnInput | str,
    decision=None,
    plan=None,
    history_window: int | None = None,
    max_context_messages: int | None = None,
    current_turn_id: int | None = None,
    visible_context: InferenceVisibleContext | None = None,
) -> LLMContext:
    if isinstance(turn_input, str):
        turn_input = build_turn_input(turn_input)
    history_window = int(history_window or settings.runtime.history_window or 8)

    if task == InferenceTask.ROUTE:
        base_visible_context = visible_context or _build_visible_context(
            state,
            turn_input,
            history_window=history_window,
            current_turn_id=current_turn_id,
            max_context_messages=int(max_context_messages or settings.runtime.router_max_context_messages or settings.runtime.max_context_messages or 8),
            profile="router",
        )
        isolate = should_isolate_current_artifact_context(state, base_visible_context, current_turn_id=current_turn_id)
        route_visible_context = base_visible_context
        if isolate:
            route_visible_context = replace(
                base_visible_context,
                session_scene="general",
                turn_scene="general_qa",
                history_messages=[],
                turn_records=[],
            )
        artifact_brief = dict(getattr(route_visible_context, "router_artifact_brief", {}) or {})
        artifact_brief_source = str(artifact_brief.get("source") or "").strip()
        text_only_router = artifact_brief_source in {"turn_result", "llm_brief"}
        chosen_model = select_router_model(
            route_visible_context,
            text_only=text_only_router,
            model=str(settings.runtime.router_model or settings.openai_config.model or settings.openai_config.intent_model).strip(),
            multimodal_model=str(settings.openai_config.multimodal_model or settings.openai_config.model).strip(),
        )
        return LLMContext(
            task=task,
            session_id=state.session_id,
            current_input=turn_input,
            history=list(route_visible_context.history_messages),
            memory=build_memory_projection(state),
            multimodal=build_multimodal_projection(route_visible_context),
            routing={
                "session_scene": route_visible_context.session_scene,
                "turn_scene": route_visible_context.turn_scene,
                "artifact_brief_source": artifact_brief_source,
                "text_only_router": text_only_router,
                "chosen_model": chosen_model,
                "isolated": isolate,
            },
            metadata={
                "visible_context": route_visible_context,
                "base_visible_context": base_visible_context,
                "current_turn_id": current_turn_id,
            },
        )

    previous_visible_context = visible_context if visible_context is not None else None
    responder_visible_context = _build_visible_context(
        state,
        turn_input,
        history_window=history_window,
        current_turn_id=current_turn_id,
        max_context_messages=int(
            max_context_messages
            or settings.runtime.responder_max_context_messages
            or settings.runtime.max_context_messages
            or 16
        ),
        profile="responder_minimal",
        previous_visible_context=previous_visible_context,
    )
    return LLMContext(
        task=task,
        session_id=state.session_id,
        current_input=turn_input,
        history=list(responder_visible_context.history_messages),
        memory=build_memory_projection(state),
        multimodal=build_multimodal_projection(responder_visible_context),
        strategy=(plan.strategy.to_metadata() if plan is not None else None),
        routing=(decision.model_dump() if decision is not None else None),
        metadata={
            "visible_context": responder_visible_context,
            "current_turn_id": current_turn_id,
        },
    )

