"""Build a turn plan directly from the router's single-round model plan.

`TurnPlan` is the handoff object between routing and execution. Once built, the
rest of the pipeline should treat the selected strategy as stable for the turn;
any memory updates should be recorded after the turn completes, not by changing
the plan mid-stream.
"""

from __future__ import annotations

from dataclasses import replace
import json

from ava.core.context.snapshot import build_context_snapshot
from ava.domain.conversation import ContextSnapshot
from ava.domain.multimodal import TurnInput
from ava.domain.routing import RouteDecision
from ava.domain.conversation.state import ConversationState
from ava.core.tracing import append_trace_log, sanitize_value
from ava.capabilities.prompt import PromptCenter
from configs import settings

from ava.pipeline.generation.model_plan_builder import build_strategy_from_model_plan
from ava.pipeline.generation.common import build_responder_messages
from .types import TurnPlan


def _compact_snapshot_trace(snapshot: ContextSnapshot) -> dict[str, object]:
    return {
        "session_id": getattr(snapshot, "session_id", ""),
        "context_profile": getattr(snapshot, "context_profile", ""),
        "user_text": getattr(snapshot, "user_text", ""),
        "session_scene": getattr(snapshot, "session_scene", ""),
        "turn_scene": getattr(snapshot, "turn_scene", ""),
        "history_messages_count": len(getattr(snapshot, "history_messages", []) or []),
        "artifacts_count": len(getattr(snapshot, "artifacts", ()) or ()),
        "reference_artifacts_count": len(getattr(snapshot, "reference_artifacts", ()) or ()),
        "router_artifact_brief": sanitize_value(getattr(snapshot, "router_artifact_brief", {}) or {}),
        "router_plan": sanitize_value(getattr(snapshot, "router_plan", {}) or {}),
    }


def _compact_responder_trace(messages: list[dict[str, object]]) -> dict[str, object]:
    if not messages:
        return {"count": 0}
    roles = [str(message.get("role", "")).strip() for message in messages]
    return {
        "count": len(messages),
        "roles": roles,
        "first_message_preview": sanitize_value(messages[0].get("content", ""), text_limit=400),
        "last_message_preview": sanitize_value(messages[-1].get("content", ""), text_limit=400),
    }


def build_turn_plan(
    state: ConversationState,
    turn_input: TurnInput | str,
    decision: RouteDecision,
    prompt_center: PromptCenter,
    history_window: int,
    max_context_messages: int | None = None,
    snapshot: ContextSnapshot | None = None,
    current_turn_id: int | None = None,
) -> TurnPlan:
    """Convert a routed turn into responder messages and strategy metadata."""
    previous_snapshot = snapshot
    if snapshot is None or getattr(snapshot, "context_profile", "full") == "router":
        # Router context is intentionally small. The responder gets a fresh
        # context profile so it can see the history/media needed to answer.
        snapshot = build_context_snapshot(
            state,
            turn_input,
            history_window,
            current_turn_id=current_turn_id,
            max_context_messages=(
                max_context_messages
                or getattr(settings.runtime, "responder_max_context_messages", 0)
                or getattr(settings.runtime, "max_context_messages", 16)
            ),
            profile="responder_minimal",
        )
        if previous_snapshot is not None:
            # Keep expensive router-side artifact analysis and the model plan so
            # the responder does not recompute planning information.
            snapshot = replace(
                snapshot,
                router_artifact_brief=dict(getattr(previous_snapshot, "router_artifact_brief", {}) or {}),
                router_plan=dict(getattr(previous_snapshot, "router_plan", {}) or {}),
            )
    # Strategy construction translates the generic router plan into the prompt
    # center's concrete branch/module/style vocabulary.
    strategy = build_strategy_from_model_plan(prompt_center, decision, snapshot)
    plan = TurnPlan(
        decision=decision,
        orchestrator_name="Model Planned Turn Orchestrator",
        strategy=strategy,
        responder_messages=build_responder_messages(prompt_center, snapshot, strategy, decision),
    )
    strategy_analysis = dict(plan.strategy.analysis or {})
    frame = dict(strategy_analysis.get("education_turn_frame") or strategy_analysis.get("task_frame") or {})
    selection_summary = {
        "session_id": getattr(snapshot, "session_id", ""),
        "turn_id": current_turn_id,
        "branch": plan.strategy.branch,
        "strategy_id": plan.strategy.strategy_id,
        "policy_id": plan.strategy.policy_id,
        "module": plan.strategy.module,
        "subject": plan.strategy.subject,
        "style": plan.strategy.style,
        "source": plan.strategy.source,
        "primary_scenario": frame.get("primary_scenario", ""),
        "primary_action": frame.get("primary_action", ""),
        "learning_objects": frame.get("learning_objects", []),
        "object_scope": frame.get("object_scope", ""),
        "object_continuity": frame.get("object_continuity", ""),
    }
    # Trace the compact plan rather than raw full prompts; raw prompts can be
    # large and may include user-provided media/text.
    append_trace_log(
        "orchestration.turn_plan.built",
        {
            "decision": sanitize_value(decision),
            "orchestrator_name": plan.orchestrator_name,
            "strategy": sanitize_value(plan.strategy),
            "strategy_analysis": sanitize_value(strategy_analysis),
            "snapshot": _compact_snapshot_trace(snapshot),
            "responder_messages": _compact_responder_trace(plan.responder_messages),
            "selection_summary": sanitize_value(selection_summary),
        },
        turn_id=current_turn_id,
        scope="orchestration",
    )
    append_trace_log(
        "turn.selection.summary",
        selection_summary,
        turn_id=current_turn_id,
        scope="selection",
    )
    print("[turn-selection]", json.dumps(sanitize_value(selection_summary), ensure_ascii=False))
    return plan


