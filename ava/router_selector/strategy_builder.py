"""推理运行时内部使用的策略构造器。"""

from __future__ import annotations

from ava.capabilities.prompt import PromptCenter, build_responder_prompt_package
from ava.domain.conversation.strategy import (
    BranchStrategy,
    EducationTurnFrame,
    PromptSelection,
    PromptSelectionTrace,
    ScenarioPolicy,
    SelectionTraceStep,
)
from ava.multi_turn_context_builder.types import ConversationContext
from ava.router_selector.schema import RouteDecision

from .education_resolver import EducationPlanResolver


def _plan(router_plan: dict | None) -> dict:
    return dict(router_plan or {})


def _normalize_task_name(branch: str, mode: str) -> str:
    """把路由层输出的 branch/mode 归一化为正式 task 名称。"""
    normalized = str(mode or "").strip().replace("_", "-")
    if branch == "clarify":
        mapping = {
            "answer-mode": "clarify-answer-mode",
            "focus": "clarify-focus",
            "missing-material": "clarify-missing-material",
            "missing-reference": "clarify-missing-reference",
            "scene": "clarify-scene",
            "subject": "clarify-subject",
        }
        return mapping.get(normalized, normalized if normalized.startswith("clarify-") else "clarify-subject")
    return normalized


def _pick_mode(branch: str, plan: dict) -> str:
    mode = str(plan.get("mode") or "").strip()
    if mode:
        return _normalize_task_name(branch, mode)
    return _normalize_task_name(branch, {
        "general_qa": "fact",
        "casual_chat": "smalltalk",
        "clarify": "clarify-subject",
    }.get(branch, "fact"))


def _build_mode_strategy_from_plan(
    prompt_center: PromptCenter,
    decision: RouteDecision,
    context: ConversationContext,
    *,
    router_plan: dict,
) -> BranchStrategy:
    del context
    plan = _plan(router_plan)
    mode = _pick_mode(decision.turn_scene, plan)
    strategy_id = f"{decision.turn_scene}.{mode}"
    selection = PromptSelection(
        branch=decision.turn_scene,
        strategy_id=strategy_id,
        mode=mode,
    )
    selection_trace = PromptSelectionTrace(
        branch=decision.turn_scene,
        steps=(
            SelectionTraceStep(
                stage="task",
                selected=mode,
                rule_path="router_model_plan",
                used_default=False,
                confidence=decision.confidence,
            ),
        ),
    )
    strategy = BranchStrategy(
        branch=decision.turn_scene,
        strategy_id=strategy_id,
        name=mode,
        description=f"{decision.turn_scene} 单轮计划：task={mode}",
        mode=mode,
        prompt_guidance=(),
        interaction_rules=(),
        analysis={
            "mode": mode,
            "selected_strategy_source": "router_model_plan",
            "router_plan": plan,
            "plan_reason": str(plan.get("plan_reason") or "").strip(),
        },
        source="router_model_plan",
        selection=selection,
        selection_trace=selection_trace,
    )
    object.__setattr__(strategy, "prompt_package", build_responder_prompt_package(prompt_center, strategy))
    return strategy


def _build_education_strategy_from_plan(
    prompt_center: PromptCenter,
    decision: RouteDecision,
    context: ConversationContext,
    *,
    router_plan: dict,
) -> BranchStrategy:
    resolver = EducationPlanResolver()
    resolved_plan = resolver.resolve(
        prompt_center=prompt_center,
        decision=decision,
        context=context,
        router_plan=router_plan,
    )
    education_plan = resolved_plan.plan
    module = education_plan.module
    subject = education_plan.subject
    pedagogy = education_plan.pedagogy
    prompt_overrides = education_plan.prompt_overrides
    learning_objects = education_plan.learning_objects or ("problem",)
    has_non_text_blocks = any(
        isinstance(block, dict) and str(block.get("type", "") or "").strip() != "input_text"
        for block in list(context.current.user_message.get("content") or [])
    )
    turn_frame = EducationTurnFrame(
        primary_scenario=education_plan.primary_scenario,
        learning_objects=learning_objects,
        object_scope=education_plan.object_scope,
        object_continuity=education_plan.object_continuity,
        primary_action=education_plan.primary_action,
        secondary_actions=education_plan.secondary_actions,
        evidence_sources=("current_turn", "recent_history"),
        scenario_policy=ScenarioPolicy(
            preserve_current_scenario=(decision.session_scene == "education"),
            allow_scene_switch=False,
            answer_boundary=education_plan.answer_boundary,
        ),
        domain_hint=subject,
        primary_modality="multimodal" if has_non_text_blocks else "text",
        requires_context=bool(context.conversation),
        requires_artifact=has_non_text_blocks,
        pedagogy_change_only=False,
        question_kind=education_plan.question_kind,
        confidence=float(education_plan.confidence or decision.confidence or 0.85),
        source="router_model",
        resolver_trace={
            "plan_reason": education_plan.plan_reason,
            "learner_state": education_plan.learner_state,
            "message_block_role": education_plan.message_block_role or "",
        },
    )

    strategy_id = f"{decision.turn_scene}.{module}.{subject}.{pedagogy}"
    selection = PromptSelection(
        branch=decision.turn_scene,
        strategy_id=strategy_id,
        module=module,
        scene=module,
        subject=subject,
        pedagogy=pedagogy,
    )
    selection_trace = PromptSelectionTrace(
        branch=decision.turn_scene,
        steps=(
            SelectionTraceStep(stage="task", selected=module, rule_path="router_model_plan", confidence=decision.confidence),
            SelectionTraceStep(stage="knowledge", selected=subject, rule_path="router_model_plan", confidence=decision.confidence),
            SelectionTraceStep(stage="method", selected=pedagogy, rule_path="router_model_plan", confidence=decision.confidence),
        ),
    )
    strategy = BranchStrategy(
        branch=decision.turn_scene,
        strategy_id=strategy_id,
        name=f"{module} / {subject} / {pedagogy}",
        description=f"{decision.turn_scene} 单轮计划：task={module}, knowledge={subject}, method={pedagogy}",
        module=module,
        scene=module,
        subject=subject,
        pedagogy=pedagogy,
        response_shape=education_plan.answer_boundary,
        teaching_objective=resolved_plan.task.purpose,
        prompt_guidance=tuple(prompt_overrides),
        interaction_rules=(),
        response_contract=dict(resolved_plan.response_contract),
        speech_policy=dict(resolved_plan.speech_policy),
        analysis={
            "subject": subject,
            "primary_scenario": turn_frame.primary_scenario,
            "primary_action": turn_frame.primary_action,
            "learning_objects": list(turn_frame.learning_objects),
            "object_scope": turn_frame.object_scope,
            "object_continuity": turn_frame.object_continuity,
            "answer_boundary": turn_frame.scenario_policy.answer_boundary,
            "learner_state": education_plan.learner_state,
            "module": module,
            "scene": module,
            "subject_axis": subject,
            "pedagogy": pedagogy,
            "selected_strategy_source": "router_model_plan",
            "education_turn_frame": turn_frame.to_metadata(),
            "router_plan": _plan(router_plan),
            "education_turn_plan": education_plan.to_metadata(),
        },
        source="router_model_plan",
        selection=selection,
        selection_trace=selection_trace,
    )
    object.__setattr__(strategy, "prompt_package", build_responder_prompt_package(prompt_center, strategy))
    return strategy


def build_strategy_from_model_plan(
    prompt_center: PromptCenter,
    decision: RouteDecision,
    context: ConversationContext,
    *,
    router_plan: dict | None = None,
) -> BranchStrategy:
    """基于 router 单轮 plan 构造正式 BranchStrategy。"""
    if decision.turn_scene == "education":
        return _build_education_strategy_from_plan(
            prompt_center,
            decision,
            context,
            router_plan=dict(router_plan or {}),
        )
    return _build_mode_strategy_from_plan(
        prompt_center,
        decision,
        context,
        router_plan=dict(router_plan or {}),
    )
