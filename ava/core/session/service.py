"""Application helpers for preparing and persisting conversation state."""

from pathlib import Path

from ava.context_engine.input import build_turn_input
from ava.pipeline.output import append_evaluation_log, build_evaluation_tags
from ava.core.tracing import append_trace_log, sanitize_turn_input, sanitize_value
from ava.domain.multimodal import TurnInput
from ava.domain.routing.schema import RouteDecision
from ava.domain.conversation.state import ConversationState
from ava.domain.conversation.strategy import BranchStrategy
from configs import BASE_DIR, settings


def load_state(state_file: str, history_window: int, session_id: str | None = None) -> ConversationState:
    path = Path(state_file)
    if not path.is_absolute():
        path = BASE_DIR / path
    state = ConversationState(
        state_file=path,
        memory_size=history_window,
        session_id=session_id or settings.runtime.default_session_id,
    )
    state.load()
    return state


def prepare_state_for_turn(state: ConversationState, turn_input: TurnInput | str) -> None:
    if isinstance(turn_input, str):
        turn_input = build_turn_input(turn_input)
    state.repair_route_state_from_turn_records()
    state.memory.update_fact_slots(turn_input.normalized_text())
    append_trace_log(
        "state.prepare_for_turn",
        {
            "session_id": state.session_id,
            "turn_input": sanitize_turn_input(turn_input),
            "session_scene": state.session_scene,
            "turn_scene": state.turn_scene,
            "memory": sanitize_value(state.memory.to_debug_payload()),
        },
        scope="state",
    )


def persist_turn(
    state: ConversationState,
    turn_input: TurnInput | str,
    assistant_text: str,
    decision: RouteDecision,
    strategy: BranchStrategy | None = None,
    llm_response_state: dict | None = None,
) -> None:
    if isinstance(turn_input, str):
        turn_input = build_turn_input(turn_input)

    state.apply_route(
        session_scene=decision.session_scene,
        turn_scene=decision.turn_scene,
        should_preserve_teaching_state=decision.should_preserve_teaching_state,
    )
    if decision.turn_scene == "education":
        state.memory.update_education_state_from_text(turn_input.normalized_text())
        if strategy is not None:
            state.memory.update_education_state_from_strategy(strategy.to_metadata(), turn_input=turn_input)
    evaluation = build_evaluation_tags(state, turn_input, decision, strategy)
    state.post_multimodal_turn(
        turn_input=turn_input,
        assistant_text=assistant_text,
        intent=decision.intent or decision.turn_scene,
        decision=decision.model_dump(),
        strategy=(strategy.to_metadata() if strategy is not None else None),
        evaluation=evaluation,
        llm_response_state=llm_response_state,
    )
    state.save()
    append_trace_log(
        "state.persist_turn",
        {
            "session_id": state.session_id,
            "turn_input": sanitize_turn_input(turn_input),
            "assistant_text": assistant_text,
            "decision": sanitize_value(decision),
            "strategy": sanitize_value(strategy.to_metadata() if strategy is not None else {}),
            "evaluation": sanitize_value(evaluation),
            "turn_records_size": len(state.turn_records),
            "conversation_state": sanitize_value(state.responder_conversation_state()),
        },
        scope="state",
    )
    append_evaluation_log(
        settings.runtime.evaluation_log_file,
        {
            "session_id": state.session_id,
            "branch": evaluation.get("branch", ""),
            "strategy_id": evaluation.get("strategy_id", ""),
            "delivery_mode": evaluation.get("delivery_mode", ""),
            "ui_mode": evaluation.get("ui_mode", ""),
            "user_followup_type": evaluation.get("user_followup_type", ""),
            "user_text": turn_input.normalized_text(),
            "assistant_text": assistant_text,
            "strategy": strategy.to_metadata() if strategy is not None else {},
            "decision": decision.model_dump(),
            "evaluation": evaluation,
        },
    )

