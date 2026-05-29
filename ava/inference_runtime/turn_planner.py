"""直接基于 router 单轮模型计划构建当前轮执行计划。"""

from __future__ import annotations

import json
from typing import Any

from ava.multi_turn_context_builder.compiler import ContextCompiler
from ava.multi_turn_context_builder.types import ConversationBuildOptions, ConversationContext
from ava.domain.multimodal import TurnInput
from ava.router_selector.schema import RouteDecision
from ava.domain.conversation.state import ConversationState
from ava.capabilities.prompt import PromptCenter
from configs import settings

from ava.pipeline.generation.model_plan_builder import build_strategy_from_model_plan
from ava.pipeline.generation.types import TurnPlan


def build_turn_plan(
    state: ConversationState,
    turn_input: TurnInput | str,
    decision: RouteDecision,
    prompt_center: PromptCenter,
    history_window: int,
    max_context_messages: int | None = None,
    context: ConversationContext | None = None,
    current_turn_id: int | None = None,
    compiler: ContextCompiler | None = None,
    router_plan: dict[str, Any] | None = None,
    artifact_brief: dict[str, Any] | None = None,
) -> TurnPlan:
    """把路由结果转换成 responder 可直接消费的执行计划。"""
    del artifact_brief
    context_compiler = compiler or ContextCompiler()
    if context is None or context.session.profile == "router":
        context = context_compiler.build_conversation_context(
            state=state,
            turn_input=turn_input,
            options=ConversationBuildOptions(
                history_window=history_window,
                current_turn_id=current_turn_id,
                max_context_messages=(
                    max_context_messages
                    or getattr(settings.runtime, "responder_max_context_messages", 0)
                    or getattr(settings.runtime, "max_context_messages", 16)
                ),
                profile="responder_minimal",
            ),
        )
    strategy = build_strategy_from_model_plan(prompt_center, decision, context, router_plan=router_plan or {})
    plan = TurnPlan(
        decision=decision,
        orchestrator_name="Model Planned Turn Orchestrator",
        strategy=strategy,
        responder_messages=context_compiler.build_responder_messages(
            context=context,
            strategy=strategy,
        ),
        router_plan=dict(router_plan or {}),
    )
    strategy_analysis = dict(plan.strategy.analysis or {})
    frame = dict(strategy_analysis.get("education_turn_frame") or strategy_analysis.get("task_frame") or {})
    selection_summary = {
        "session_id": context.session.session_id,
        "turn_id": current_turn_id,
        "branch": plan.strategy.branch,
        "strategy_id": plan.strategy.strategy_id,
        "policy_id": plan.strategy.policy_id,
        "module": plan.strategy.module,
        "subject": plan.strategy.subject,
        "pedagogy": plan.strategy.pedagogy,
        "source": plan.strategy.source,
        "primary_scenario": frame.get("primary_scenario", ""),
        "primary_action": frame.get("primary_action", ""),
        "learning_objects": frame.get("learning_objects", []),
        "object_scope": frame.get("object_scope", ""),
        "object_continuity": frame.get("object_continuity", ""),
    }
    print("[turn-selection]", json.dumps(selection_summary, ensure_ascii=False))
    return plan
