"""Build BranchStrategy directly from a single router model planning result."""

from __future__ import annotations

from typing import Any

from ava.domain.context import ContextSnapshot
from ava.domain.routing import RouteDecision
from ava.domain.strategy import (
    BranchStrategy,
    EducationTurnFrame,
    PromptSelection,
    PromptSelectionTrace,
    ResolvedPromptSpec,
    ScenarioPolicy,
    SelectionTraceStep,
)
from ava.infrastructure.prompts import ComposedPromptRuntime, PromptCenter, SimpleBranchPromptRuntime


_GENERAL_MODES = {"confirm", "troubleshoot", "compare", "visual", "howto", "reasoned", "fact"}
_CHAT_MODES = {"reaction", "praise", "backchannel", "companion", "humor", "smalltalk"}
_CLARIFY_MODES = {"missing_material", "focus", "missing_reference", "answer_mode", "scene", "subject"}


def _plan(snapshot: ContextSnapshot) -> dict[str, Any]:
    return dict(getattr(snapshot, "router_plan", {}) or {})


def _string_list(value: Any) -> tuple[str, ...]:
    return tuple(str(item).strip() for item in (value or []) if str(item).strip())


def _pick_mode(branch: str, plan: dict[str, Any]) -> str:
    mode = str(plan.get("mode") or "").strip()
    if branch == "general_qa" and mode in _GENERAL_MODES:
        return mode
    if branch == "casual_chat" and mode in _CHAT_MODES:
        return mode
    if branch == "clarify" and mode in _CLARIFY_MODES:
        return mode
    return {
        "general_qa": "fact",
        "casual_chat": "smalltalk",
        "clarify": "subject",
    }.get(branch, "fact")


def _build_mode_strategy_from_plan(
    prompt_center: PromptCenter,
    decision: RouteDecision,
    snapshot: ContextSnapshot,
) -> BranchStrategy:
    plan = _plan(snapshot)
    runtime = SimpleBranchPromptRuntime(prompt_center)
    plugin = runtime.load_plugin(decision.turn_scene)
    mode = _pick_mode(decision.turn_scene, plan)
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
    snapshot: ContextSnapshot,
) -> BranchStrategy:
    plan = _plan(snapshot)
    runtime = ComposedPromptRuntime(prompt_center)
    plugin = runtime.load_plugin()

    module = str(plan.get("module") or "solve").strip() or "solve"
    if module not in set(runtime.list_module_ids()):
        module = "solve"

    subject = str(plan.get("subject") or "general").strip() or "general"
    if subject not in set(runtime.list_subject_ids(module)):
        subject = "general"

    style = str(plan.get("style") or "step_by_step").strip() or "step_by_step"
    if style not in set(runtime.list_style_ids(module)):
        style = "step_by_step"

    module_asset = runtime.load_module(module)
    subject_asset = runtime.load_subject(module, subject)
    style_asset = runtime.load_style(module, style)

    output_defaults = dict(module_asset.output_defaults or {})
    style_output = dict(style_asset.output_adjustments or {})
    subject_ui_hints = dict(subject_asset.ui_hints or {})
    delivery_mode = str(output_defaults.get("delivery_mode", "speech_ui_dual")).strip() or "speech_ui_dual"
    module_ui_mode = str(output_defaults.get("ui_mode", "")).strip()
    if module_ui_mode == "none":
        ui_mode = "none"
    else:
        ui_mode = str(subject_ui_hints.get("ui_mode_default", "")).strip() or module_ui_mode or "learning_card"

    answer_boundary = str(plan.get("answer_boundary") or "direct_explain").strip() or "direct_explain"
    policy_id = str(plan.get("policy_id") or "").strip()
    prompt_overrides = _string_list(plan.get("prompt_overrides"))
    learning_objects = _string_list(plan.get("learning_objects")) or ("problem",)
    turn_frame = EducationTurnFrame(
        primary_scenario=str(plan.get("primary_scenario") or "practice").strip() or "practice",
        learning_objects=learning_objects,
        object_scope=str(plan.get("object_scope") or "whole_problem").strip() or "whole_problem",
        object_continuity=str(plan.get("object_continuity") or "uncertain").strip() or "uncertain",
        primary_action=str(plan.get("primary_action") or "solve_current_problem").strip() or "solve_current_problem",
        secondary_actions=_string_list(plan.get("secondary_actions")),
        evidence_sources=("current_turn", "recent_history"),
        scenario_policy=ScenarioPolicy(
            preserve_current_scenario=(decision.session_scene == "education"),
            allow_scene_switch=False,
            answer_boundary=answer_boundary,
        ),
        domain_hint=subject,
        primary_modality=("multimodal" if snapshot.artifacts or snapshot.reference_artifacts else "text"),
        requires_context=bool(snapshot.history_messages or snapshot.recent_turns_summary),
        requires_artifact=bool(snapshot.artifacts or snapshot.reference_artifacts),
        style_change_only=False,
        question_kind=str(plan.get("question_kind") or "").strip() or None,
        confidence=float(plan.get("confidence") or decision.confidence or 0.85),
        source="router_model",
        resolver_trace={"plan_reason": str(plan.get("plan_reason") or "").strip()},
    )

    final_analysis = {
        "subject": subject,
        "primary_scenario": turn_frame.primary_scenario,
        "primary_action": turn_frame.primary_action,
        "learning_objects": list(turn_frame.learning_objects),
        "object_scope": turn_frame.object_scope,
        "object_continuity": turn_frame.object_continuity,
        "answer_boundary": turn_frame.scenario_policy.answer_boundary,
        "module": module,
        "scene": module,
        "subject_axis": subject,
        "style": style,
        "selected_strategy_id": f"{decision.turn_scene}.{module}.{subject}.{style}",
        "selected_policy_id": policy_id,
        "selected_strategy_source": "router_model_plan",
        "education_turn_frame": turn_frame.to_metadata(),
        "task_frame": turn_frame.to_metadata(),
        "scenario_prompt_overrides": list(prompt_overrides),
        "prompt_context_policy": {},
        "router_plan": plan,
    }

    instructions = tuple(
        dict.fromkeys(
            [
                *plugin.rules,
                *module_asset.global_rules,
                *module_asset.instructions,
                *subject_asset.instructions,
                *style_asset.instructions,
                *prompt_overrides,
            ]
        )
    )
    subject_focus = tuple(subject_asset.focus)
    strategy_id = f"{decision.turn_scene}.{module}.{subject}.{style}"
    selection = PromptSelection(
        branch=decision.turn_scene,
        strategy_id=strategy_id,
        delivery_mode=delivery_mode,
        ui_mode=ui_mode,
        policy_id=policy_id,
        module=module,
        scene=module,
        subject=subject,
        style=style,
    )
    selection_trace = PromptSelectionTrace(
        branch=decision.turn_scene,
        steps=(
            SelectionTraceStep(stage="module", selected=module, rule_path="router_model_plan", confidence=decision.confidence),
            SelectionTraceStep(stage="subject", selected=subject, rule_path="router_model_plan", confidence=decision.confidence),
            SelectionTraceStep(stage="style", selected=style, rule_path="router_model_plan", confidence=decision.confidence),
        ),
    )
    resolved_prompt_spec = ResolvedPromptSpec(
        branch=decision.turn_scene,
        strategy_id=strategy_id,
        base_files=(
            "core/base/persona.md",
            "core/base/multimodal_rules.md",
        ),
        contract_file=f"core/contracts/{delivery_mode}.md",
        renderer_file="core/renderer/education_renderer.md",
        variables={
            "plugin": plugin,
            "module": module_asset,
            "subject": subject_asset,
            "style": style_asset,
        },
    )
    return BranchStrategy(
        branch=decision.turn_scene,
        strategy_id=strategy_id,
        name=f"{module_asset.name} / {subject_asset.name} / {style_asset.name}",
        description=f"{decision.turn_scene} 单次模型规划策略：module={module}, subject={subject}, style={style}",
        render_template="core/renderer/education_renderer.md",
        delivery_mode=delivery_mode,
        ui_mode=ui_mode,
        policy_id=policy_id,
        module=module,
        scene=module,
        subject=subject,
        style=style,
        response_shape=" / ".join(module_asset.response_structure),
        teaching_objective=module_asset.goal,
        student_snapshot="由 router 单次模型规划直接确定当前轮教学动作与表达方式。",
        prompt_guidance=instructions,
        teacher_moves=subject_focus,
        interaction_rules=tuple(dict.fromkeys([*module_asset.interaction_policy, *style_asset.constraints])),
        common_misconceptions=subject_asset.common_mistakes,
        behavior_do=module_asset.global_rules,
        success_criteria=subject_focus,
        next_turn_goal="围绕当前轮规划直接回答，不再追加第二轮策略判定。",
        response_contract={
            "module": module,
            "style": style,
            **output_defaults,
            **style_output,
        },
        speech_policy={"tone": style_asset.tone, "plugin": plugin.asset_id, "policy_id": policy_id},
        ui_policy={"ui_mode_default": ui_mode},
        analysis=final_analysis,
        source="router_model_plan",
        selection=selection,
        selection_trace=selection_trace,
        resolved_prompt_spec=resolved_prompt_spec,
    )


def build_strategy_from_model_plan(
    prompt_center: PromptCenter,
    decision: RouteDecision,
    snapshot: ContextSnapshot,
) -> BranchStrategy:
    if decision.turn_scene == "education":
        return _build_education_strategy_from_plan(prompt_center, decision, snapshot)
    return _build_mode_strategy_from_plan(prompt_center, decision, snapshot)
