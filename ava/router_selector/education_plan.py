"""推理运行时使用的教育单轮计划模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _string_tuple(value: Any) -> tuple[str, ...]:
    """把任意列表值收敛为去空白的字符串元组。"""
    return tuple(str(item).strip() for item in (value or []) if str(item).strip())


@dataclass(frozen=True)
class EducationTurnPlan:
    """描述教育场景下当前轮教学计划。"""

    branch: str = "education"
    module: str = "solve"
    subject: str = "general"
    pedagogy: str = "step_by_step"
    answer_boundary: str = "direct_explain"
    learner_state: str = "followup"
    primary_scenario: str = "practice"
    primary_action: str = "solve_current_problem"
    learning_objects: tuple[str, ...] = ("problem",)
    object_scope: str = "whole_problem"
    object_continuity: str = "uncertain"
    question_kind: str | None = None
    message_block_role: str | None = None
    ui_mode_hint: str | None = None
    policy_id: str = ""
    prompt_overrides: tuple[str, ...] = ()
    secondary_actions: tuple[str, ...] = ()
    confidence: float = 0.0
    plan_reason: str = ""
    raw_plan: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any] | None,
        *,
        confidence: float = 0.0,
    ) -> "EducationTurnPlan":
        """从 router 原始 plan 字典构建计划对象。"""
        data = dict(payload or {})
        pedagogy = str(data.get("pedagogy") or data.get("style") or "step_by_step").strip() or "step_by_step"
        return cls(
            module=str(data.get("module") or "solve").strip() or "solve",
            subject=str(data.get("subject") or "general").strip() or "general",
            pedagogy=pedagogy,
            answer_boundary=str(data.get("answer_boundary") or "direct_explain").strip() or "direct_explain",
            learner_state=str(data.get("learner_state") or "").strip() or "followup",
            primary_scenario=str(data.get("primary_scenario") or "practice").strip() or "practice",
            primary_action=str(data.get("primary_action") or "solve_current_problem").strip() or "solve_current_problem",
            learning_objects=_string_tuple(data.get("learning_objects")) or ("problem",),
            object_scope=str(data.get("object_scope") or "whole_problem").strip() or "whole_problem",
            object_continuity=str(data.get("object_continuity") or "uncertain").strip() or "uncertain",
            question_kind=(str(data.get("question_kind") or "").strip() or None),
            message_block_role=(str(data.get("message_block_role") or "").strip() or None),
            ui_mode_hint=(str(data.get("ui_mode_hint") or "").strip() or None),
            policy_id=str(data.get("policy_id") or "").strip(),
            prompt_overrides=_string_tuple(data.get("prompt_overrides")),
            secondary_actions=_string_tuple(data.get("secondary_actions")),
            confidence=float(data.get("confidence") or confidence or 0.0),
            plan_reason=str(data.get("plan_reason") or "").strip(),
            raw_plan=data,
        )

    def to_metadata(self) -> dict[str, Any]:
        """转为稳定可记录的元数据。"""
        return {
            "branch": self.branch,
            "module": self.module,
            "subject": self.subject,
            "pedagogy": self.pedagogy,
            "answer_boundary": self.answer_boundary,
            "learner_state": self.learner_state,
            "primary_scenario": self.primary_scenario,
            "primary_action": self.primary_action,
            "learning_objects": list(self.learning_objects),
            "object_scope": self.object_scope,
            "object_continuity": self.object_continuity,
            "question_kind": self.question_kind or "",
            "message_block_role": self.message_block_role or "",
            "ui_mode_hint": self.ui_mode_hint or "",
            "policy_id": self.policy_id,
            "prompt_overrides": list(self.prompt_overrides),
            "secondary_actions": list(self.secondary_actions),
            "confidence": round(float(self.confidence), 4),
            "plan_reason": self.plan_reason,
            "raw_plan": dict(self.raw_plan),
        }

