"""Build BranchStrategy directly from a single router model planning result."""

from __future__ import annotations

from typing import Any

from ava.capabilities.prompt import BranchPromptRuntime, PromptCenter
from ava.multi_turn_context_builder.types import ConversationContext
from ava.pipeline.generation.education_resolver import EducationPlanResolver
from ava.router_selector.schema import RouteDecision
from ava.domain.conversation.strategy import (
    BranchStrategy,
    EducationTurnFrame,
    PromptSelection,
    PromptSelectionTrace,
    ResolvedPromptSpec,
    ScenarioPolicy,
    SelectionTraceStep,
)


def _plan(router_plan: dict[str, Any] | None) -> dict[str, Any]:
    return dict(router_plan or {})


def _string_list(value: Any) -> tuple[str, ...]:
    return tuple(str(item).strip() for item in (value or []) if str(item).strip())


def _pick_mode(branch: str, plan: dict[str, Any]) -> str:
    mode = str(plan.get("mode") or "").strip()
    if mode:
        return mode
    return {
        "general_qa": "fact",
        "casual_chat": "smalltalk",
        "clarify": "subject",
    }.get(branch, "fact")


def _build_mode_strategy_from_plan(
    prompt_center: PromptCenter,
    decision: RouteDecision,
    context: ConversationContext,
    *,
    router_plan: dict[str, Any],
) -> BranchStrategy:
    plan = _plan(router_plan)
    runtime = BranchPromptRuntime(prompt_center)
    plugin = runtime.load_plugin(decision.turn_scene)
    mode = _pick_mode(decision.turn_scene, plan)
    try:
        mode_asset = runtime.load_mode(decision.turn_scene, mode)
    except FileNotFoundError:
        mode = {
            "general_qa": "fact",
            "casual_chat": "smalltalk",
            "clarify": "subject",
        }.get(decision.turn_scene, "fact")
        mode_asset = runtime.load_mode(decision.turn_scene, mode)

    strategy_id = f"{decision.turn_scene}.{mode}"
    final_analysis = {
        "mode": mode,
        "selected_strategy_id": strategy_id,
        "selected_strategy_source": "router_model_plan",
        "router_plan": plan,
        "plan_reason": str(plan.get("plan_reason") or "").strip(),
    }
    selection = PromptSelection(
        branch=decision.turn_scene,
        strategy_id=strategy_id,
        delivery_mode=mode_asset.delivery_mode,
        ui_mode=mode_asset.ui_mode,
        mode=mode,
    )
    selection_trace = PromptSelectionTrace(
        branch=decision.turn_scene,
        steps=(
            SelectionTraceStep(
                stage="mode",
                selected=mode,
                rule_path="router_model_plan",
                used_default=False,
                confidence=decision.confidence,
            ),
        ),
    )
    resolved_prompt_spec = ResolvedPromptSpec(
        branch=decision.turn_scene,
        strategy_id=strategy_id,
        base_files=(
            "core/base/persona.md",
            "core/base/multimodal_rules.md",
        ),
        contract_file=f"core/contracts/{mode_asset.delivery_mode}.md",
        renderer_file="core/renderer/mode_renderer.md",
        variables={
            "plugin": plugin,
            "branch": decision.turn_scene,
            "selection": selection,
            "mode": mode_asset,
            "delivery_mode": mode_asset.delivery_mode,
            "ui_mode": mode_asset.ui_mode,
            "selection_trace": selection_trace,
        },
    )
    return BranchStrategy(
        branch=decision.turn_scene,
        strategy_id=strategy_id,
        name=mode_asset.name,
        description=mode_asset.description,
        render_template="core/renderer/mode_renderer.md",
        delivery_mode=mode_asset.delivery_mode,
        ui_mode=mode_asset.ui_mode,
        mode=mode,
        response_shape=mode_asset.response_shape,
        teaching_objective=mode_asset.objective,
        student_snapshot="由 router 单次模型规划直接选择当前轮的最小必要回答模式。",
        prompt_guidance=mode_asset.instructions,
        interaction_rules=mode_asset.interaction_rules,
        example_cases=mode_asset.examples,
        response_contract=dict(mode_asset.response_contract or {}),
        speech_policy=dict(mode_asset.speech_policy or {}),
        ui_policy=dict(mode_asset.ui_policy or {}),
        analysis=final_analysis,
        source="router_model_plan",
        selection=selection,
        selection_trace=selection_trace,
        resolved_prompt_spec=resolved_prompt_spec,
    )


def _build_education_strategy_from_plan(
    prompt_center: PromptCenter,
    decision: RouteDecision,
    context: ConversationContext,
    *,
    router_plan: dict[str, Any],
) -> BranchStrategy:
    resolver = EducationPlanResolver()
    resolved_plan = resolver.resolve(
        prompt_center=prompt_center,
        decision=decision,
        context=context,
        router_plan=router_plan,
    )
    education_plan = resolved_plan.plan
    assets = resolved_plan.assets
    plugin = assets.branch
    module_asset = assets.module
    subject_asset = assets.subject
    pedagogy_asset = assets.pedagogy
    module = education_plan.module
    subject = education_plan.subject
    pedagogy = education_plan.pedagogy
    policy_id = education_plan.policy_id
    prompt_overrides = education_plan.prompt_overrides
    learning_objects = education_plan.learning_objects or ("problem",)
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
        primary_modality=("multimodal" if context.current.artifacts else "text"),
        requires_context=bool(context.conversation),
        requires_artifact=bool(context.current.artifacts),
        pedagogy_change_only=False,
        question_kind=education_plan.question_kind,
        confidence=float(education_plan.confidence or decision.confidence or 0.85),
        source="router_model",
        resolver_trace={
            "plan_reason": education_plan.plan_reason,
            "learner_state": education_plan.learner_state,
            "artifact_role": education_plan.artifact_role or "",
        },
    )

    final_analysis = {
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
        "selected_strategy_id": f"{decision.turn_scene}.{module}.{subject}.{pedagogy}",
        "selected_policy_id": policy_id,
        "selected_strategy_source": "router_model_plan",
        "education_turn_frame": turn_frame.to_metadata(),
        "task_frame": turn_frame.to_metadata(),
        "scenario_prompt_overrides": list(prompt_overrides),
        "prompt_context_policy": {},
        "router_plan": _plan(router_plan),
        "education_turn_plan": education_plan.to_metadata(),
    }

    instructions = tuple(
        dict.fromkeys(
            [
                *plugin.rules,
                *module_asset.global_rules,
                *module_asset.instructions,
                *subject_asset.instructions,
                *pedagogy_asset.instructions,
                *prompt_overrides,
            ]
        )
    )
    subject_focus = tuple(subject_asset.focus)
    strategy_id = f"{decision.turn_scene}.{module}.{subject}.{pedagogy}"
    selection = PromptSelection(
        branch=decision.turn_scene,
        strategy_id=strategy_id,
        delivery_mode=resolved_plan.delivery_mode,
        ui_mode=resolved_plan.ui_mode,
        policy_id=policy_id,
        module=module,
        scene=module,
        subject=subject,
        pedagogy=pedagogy,
    )
    selection_trace = PromptSelectionTrace(
        branch=decision.turn_scene,
        steps=(
            SelectionTraceStep(stage="module", selected=module, rule_path="router_model_plan", confidence=decision.confidence),
            SelectionTraceStep(stage="subject", selected=subject, rule_path="router_model_plan", confidence=decision.confidence),
            SelectionTraceStep(stage="pedagogy", selected=pedagogy, rule_path="router_model_plan", confidence=decision.confidence),
        ),
    )
    resolved_prompt_spec = ResolvedPromptSpec(
        branch=decision.turn_scene,
        strategy_id=strategy_id,
        base_files=(
            "core/base/persona.md",
            "core/base/multimodal_rules.md",
        ),
        contract_file=f"core/contracts/{resolved_plan.delivery_mode}.md",
        renderer_file="core/renderer/education_renderer.md",
        variables={
            "plugin": plugin,
            "module": module_asset,
            "subject": subject_asset,
            "pedagogy": pedagogy_asset,
            "education_plan": education_plan.to_metadata(),
        },
    )
    return BranchStrategy(
        branch=decision.turn_scene,
        strategy_id=strategy_id,
        name=f"{module_asset.name} / {subject_asset.name} / {pedagogy_asset.name}",
        description=f"{decision.turn_scene} 单次模型规划策略: module={module}, subject={subject}, pedagogy={pedagogy}",
        render_template="core/renderer/education_renderer.md",
        delivery_mode=resolved_plan.delivery_mode,
        ui_mode=resolved_plan.ui_mode,
        policy_id=policy_id,
        module=module,
        scene=module,
        subject=subject,
        pedagogy=pedagogy,
        response_shape=" / ".join(module_asset.response_structure),
        teaching_objective=module_asset.goal,
        student_snapshot="由 router 单次模型规划直接确定当前轮教学动作与表达方式。",
        prompt_guidance=instructions,
        teacher_moves=subject_focus,
        interaction_rules=tuple(dict.fromkeys([*module_asset.interaction_policy, *pedagogy_asset.constraints])),
        common_misconceptions=subject_asset.common_mistakes,
        behavior_do=module_asset.global_rules,
        success_criteria=subject_focus,
        next_turn_goal="围绕当前轮规划直接回答，不再追加第二轮策略判定。",
        response_contract=dict(resolved_plan.response_contract),
        speech_policy={"tone": pedagogy_asset.tone, "plugin": plugin.asset_id, **dict(resolved_plan.speech_policy)},
        ui_policy={"ui_mode_default": resolved_plan.ui_mode},
        analysis=final_analysis,
        source="router_model_plan",
        selection=selection,
        selection_trace=selection_trace,
        resolved_prompt_spec=resolved_prompt_spec,
    )


def build_strategy_from_model_plan(
    prompt_center: PromptCenter,
    decision: RouteDecision,
    context: ConversationContext,
    *,
    router_plan: dict[str, Any] | None = None,
) -> BranchStrategy:
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
