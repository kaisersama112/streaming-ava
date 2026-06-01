"""Structured branch-strategy model used by the prompt runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ava.capabilities.prompt.specs import (
        BranchSpec,
        ModeSpec,
        ModuleSpec,
        PedagogySpec,
        PromptSkillCard,
        SubjectSpec,
    )


def _safe_meta_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _safe_meta_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe_meta_value(item) for item in value]
    if hasattr(value, "to_metadata") and callable(value.to_metadata):
        return value.to_metadata()
    return str(value)


@dataclass(frozen=True)
class PromptSelection:
    branch: str
    strategy_id: str
    delivery_mode: str
    ui_mode: str
    policy_id: str = ""
    mode: str = ""
    module: str = ""
    scene: str = ""
    subject: str = ""
    pedagogy: str = ""

    def to_metadata(self) -> dict[str, Any]:
        return {
            "branch": self.branch,
            "strategy_id": self.strategy_id,
            "delivery_mode": self.delivery_mode,
            "ui_mode": self.ui_mode,
            "policy_id": self.policy_id,
            "mode": self.mode,
            "module": self.module,
            "scene": self.scene,
            "subject": self.subject,
            "pedagogy": self.pedagogy,
        }


@dataclass(frozen=True)
class SelectionTraceStep:
    stage: str
    selected: str
    rule_path: str
    matched_rule_index: int | None = None
    matched_when: dict[str, Any] = field(default_factory=dict)
    used_default: bool = False
    default_value: str = ""
    candidates: tuple[str, ...] = ()
    confidence: float | None = None

    def to_metadata(self) -> dict[str, Any]:
        return {
            "layer": self.stage,
            "selected": self.selected,
            "rule_path": self.rule_path,
            "matched_rule_index": self.matched_rule_index,
            "matched_when": dict(self.matched_when),
            "used_default": self.used_default,
            "default_value": self.default_value,
            "candidates": list(self.candidates),
            "confidence": self.confidence,
        }


@dataclass(frozen=True)
class PromptSelectionTrace:
    branch: str
    steps: tuple[SelectionTraceStep, ...] = ()

    def to_metadata(self) -> dict[str, Any]:
        return {
            "plugin": self.branch,
            "layer_results": [step.to_metadata() for step in self.steps],
        }


@dataclass(frozen=True)
class ResolvedPromptSpec:
    branch: str
    strategy_id: str
    composition: str
    delivery_mode: str
    branch_skill: "PromptSkillCard"
    branch_spec: "BranchSpec"
    mode_skill: "PromptSkillCard | None" = None
    mode_spec: "ModeSpec | None" = None
    module_skill: "PromptSkillCard | None" = None
    module_spec: "ModuleSpec | None" = None
    subject_skill: "PromptSkillCard | None" = None
    subject_spec: "SubjectSpec | None" = None
    pedagogy_skill: "PromptSkillCard | None" = None
    pedagogy_spec: "PedagogySpec | None" = None

    def to_metadata(self) -> dict[str, Any]:
        return {
            "branch": self.branch,
            "strategy_id": self.strategy_id,
            "composition": self.composition,
            "delivery_mode": self.delivery_mode,
            "branch_skill_id": getattr(self.branch_skill, "asset_id", ""),
            "branch_spec_id": getattr(self.branch_spec, "asset_id", ""),
            "mode_skill_id": getattr(self.mode_skill, "asset_id", ""),
            "mode_spec_id": getattr(self.mode_spec, "asset_id", ""),
            "module_skill_id": getattr(self.module_skill, "asset_id", ""),
            "module_spec_id": getattr(self.module_spec, "asset_id", ""),
            "subject_skill_id": getattr(self.subject_skill, "asset_id", ""),
            "subject_spec_id": getattr(self.subject_spec, "asset_id", ""),
            "pedagogy_skill_id": getattr(self.pedagogy_skill, "asset_id", ""),
            "pedagogy_spec_id": getattr(self.pedagogy_spec, "asset_id", ""),
        }


@dataclass(frozen=True)
class ScenarioPolicy:
    preserve_current_scenario: bool
    allow_scene_switch: bool
    answer_boundary: str

    def to_metadata(self) -> dict[str, Any]:
        return {
            "preserve_current_scenario": self.preserve_current_scenario,
            "allow_scene_switch": self.allow_scene_switch,
            "answer_boundary": self.answer_boundary,
        }


@dataclass(frozen=True)
class EducationTurnFrame:
    primary_scenario: str
    learning_objects: tuple[str, ...]
    object_scope: str
    object_continuity: str
    primary_action: str
    secondary_actions: tuple[str, ...]
    evidence_sources: tuple[str, ...]
    scenario_policy: ScenarioPolicy
    domain_hint: str | None
    primary_modality: str
    requires_context: bool
    requires_artifact: bool
    pedagogy_change_only: bool
    question_kind: str | None = None
    confidence: float = 0.0
    source: str = "local"
    resolver_trace: dict[str, Any] = field(default_factory=dict)

    def to_metadata(self) -> dict[str, Any]:
        return {
            "primary_scenario": self.primary_scenario,
            "learning_objects": list(self.learning_objects),
            "object_scope": self.object_scope,
            "object_continuity": self.object_continuity,
            "primary_action": self.primary_action,
            "secondary_actions": list(self.secondary_actions),
            "evidence_sources": list(self.evidence_sources),
            "scenario_policy": self.scenario_policy.to_metadata(),
            "domain_hint": self.domain_hint or "",
            "primary_modality": self.primary_modality,
            "requires_context": self.requires_context,
            "requires_artifact": self.requires_artifact,
            "pedagogy_change_only": self.pedagogy_change_only,
            "question_kind": self.question_kind or "",
            "confidence": round(float(self.confidence), 4),
            "source": self.source,
            "resolver_trace": _safe_meta_value(self.resolver_trace),
        }


@dataclass(frozen=True)
class BranchStrategy:
    branch: str
    strategy_id: str
    name: str
    description: str
    render_template: str
    delivery_mode: str
    ui_mode: str
    policy_id: str = ""
    mode: str = ""
    module: str = ""
    scene: str = ""
    subject: str = ""
    pedagogy: str = ""
    response_shape: str = ""
    teaching_objective: str = ""
    student_snapshot: str = ""
    prompt_guidance: tuple[str, ...] = ()
    teacher_moves: tuple[str, ...] = ()
    interaction_rules: tuple[str, ...] = ()
    common_misconceptions: tuple[str, ...] = ()
    behavior_do: tuple[str, ...] = ()
    behavior_avoid: tuple[str, ...] = ()
    success_criteria: tuple[str, ...] = ()
    next_turn_goal: str = ""
    example_cases: tuple[str, ...] = ()
    response_contract: dict[str, Any] = field(default_factory=dict)
    speech_policy: dict[str, Any] = field(default_factory=dict)
    ui_policy: dict[str, Any] = field(default_factory=dict)
    analysis: dict[str, Any] = field(default_factory=dict)
    source: str = "rules"
    selection: PromptSelection | None = None
    selection_trace: PromptSelectionTrace | None = None
    resolved_prompt_spec: ResolvedPromptSpec | None = None

    def to_metadata(self) -> dict[str, Any]:
        return {
            "branch": self.branch,
            "strategy_id": self.strategy_id,
            "name": self.name,
            "description": self.description,
            "render_template": self.render_template,
            "delivery_mode": self.delivery_mode,
            "ui_mode": self.ui_mode,
            "policy_id": self.policy_id,
            "mode": self.mode,
            "module": self.module,
            "scene": self.scene,
            "subject": self.subject,
            "pedagogy": self.pedagogy,
            "response_shape": self.response_shape,
            "teaching_objective": self.teaching_objective,
            "student_snapshot": self.student_snapshot,
            "prompt_guidance": list(self.prompt_guidance),
            "teacher_moves": list(self.teacher_moves),
            "interaction_rules": list(self.interaction_rules),
            "common_misconceptions": list(self.common_misconceptions),
            "behavior_do": list(self.behavior_do),
            "behavior_avoid": list(self.behavior_avoid),
            "success_criteria": list(self.success_criteria),
            "next_turn_goal": self.next_turn_goal,
            "example_cases": list(self.example_cases),
            "response_contract": dict(self.response_contract),
            "speech_policy": dict(self.speech_policy),
            "ui_policy": dict(self.ui_policy),
            "analysis": dict(self.analysis),
            "source": self.source,
            "selection": self.selection.to_metadata() if self.selection is not None else {},
            "selection_trace": self.selection_trace.to_metadata() if self.selection_trace is not None else {},
            "resolved_prompt_spec": (
                self.resolved_prompt_spec.to_metadata() if self.resolved_prompt_spec is not None else {}
            ),
        }
