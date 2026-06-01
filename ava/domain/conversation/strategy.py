"""会话域中的结构化策略对象。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _safe_meta_value(value: Any) -> Any:
    """把复杂对象安全转换为可落盘的元数据。"""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _safe_meta_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe_meta_value(item) for item in value]
    if hasattr(value, "to_metadata") and callable(value.to_metadata):
        return value.to_metadata()
    return str(value)


@dataclass(frozen=True)
class PromptSelection:
    """路由阶段选出的结构化技能组合。"""

    branch: str
    strategy_id: str
    mode: str = ""
    module: str = ""
    scene: str = ""
    subject: str = ""
    pedagogy: str = ""

    def to_metadata(self) -> dict[str, Any]:
        return {
            "branch": self.branch,
            "mode": self.mode,
            "module": self.module,
            "scene": self.scene,
            "subject": self.subject,
            "pedagogy": self.pedagogy,
        }


@dataclass(frozen=True)
class SelectionTraceStep:
    """单步选择轨迹。"""

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
    """多步选择轨迹。"""

    branch: str
    steps: tuple[SelectionTraceStep, ...] = ()

    def to_metadata(self) -> dict[str, Any]:
        return {
            "branch": self.branch,
            "steps": [step.to_metadata() for step in self.steps],
        }


@dataclass(frozen=True)
class ScenarioPolicy:
    """教育场景延续策略。"""

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
    """教育场景下单轮分析框架。"""

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
    """当前轮的结构化执行策略。

    `strategy_id` 仅作为内部缓存、调试和去重标识使用，
    不再作为正式运行时语义对外暴露。

    `name` / `description` 仅保留给内部调试阅读，
    不再进入正式元数据、状态落盘或运行时主语义。
    """

    branch: str
    strategy_id: str
    name: str
    description: str
    mode: str = ""
    module: str = ""
    scene: str = ""
    subject: str = ""
    pedagogy: str = ""
    prompt_package: Any | None = None
    response_shape: str = ""
    teaching_objective: str = ""
    prompt_guidance: tuple[str, ...] = ()
    interaction_rules: tuple[str, ...] = ()
    response_contract: dict[str, Any] = field(default_factory=dict)
    speech_policy: dict[str, Any] = field(default_factory=dict)
    analysis: dict[str, Any] = field(default_factory=dict)
    source: str = "rules"
    selection: PromptSelection | None = None
    selection_trace: PromptSelectionTrace | None = None

    def prompt_profile(self) -> dict[str, Any]:
        """返回当前策略绑定的 PromptPackage 运行时视图。"""
        package = self.prompt_package
        if package is None or not hasattr(package, "runtime_profile"):
            return {}
        return dict(package.runtime_profile())

    def to_metadata(self) -> dict[str, Any]:
        prompt_profile = self.prompt_profile()
        prompt_package = (
            self.prompt_package.to_metadata()
            if self.prompt_package is not None and hasattr(self.prompt_package, "to_metadata")
            else {}
        )
        return {
            "branch": self.branch,
            "mode": self.mode,
            "module": self.module,
            "scene": self.scene,
            "subject": self.subject,
            "pedagogy": self.pedagogy,
            "response_shape": self.response_shape,
            "teaching_objective": self.teaching_objective,
            "prompt_guidance": list(self.prompt_guidance),
            "interaction_rules": list(self.interaction_rules),
            "response_contract": dict(self.response_contract),
            "speech_policy": dict(self.speech_policy),
            "analysis": dict(self.analysis),
            "source": self.source,
            "selection": self.selection.to_metadata() if self.selection is not None else {},
            "selection_trace": self.selection_trace.to_metadata() if self.selection_trace is not None else {},
            "prompt_profile": prompt_profile,
            "prompt_package": prompt_package,
        }
