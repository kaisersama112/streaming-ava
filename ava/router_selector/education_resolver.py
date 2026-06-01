"""教育计划解析器。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ava.capabilities.prompt.loaders import PromptSkillLoader
from ava.capabilities.prompt.prompt_loader import PromptCenter
from ava.capabilities.prompt.specs import Skill
from ava.multi_turn_context_builder.types import ConversationContext
from ava.router_selector.schema import RouteDecision

from .education_plan import EducationTurnPlan


@dataclass(frozen=True)
class ResolvedEducationPlan:
    """解析后的教育计划。"""

    plan: EducationTurnPlan
    capability: Skill
    task: Skill
    knowledge: Skill
    method: Skill
    response_contract: dict[str, Any]
    speech_policy: dict[str, Any]


class EducationPlanResolver:
    """把 router 的教育计划归一化为可执行计划。"""

    _VALID_BOUNDARIES = {
        "hint_first",
        "targeted_answer",
        "direct_explain",
        "full_solution",
        "contextual_only",
    }
    _VALID_LEARNER_STATES = {
        "blocked",
        "verifying",
        "confused",
        "followup",
        "switched_topic",
    }

    def resolve(
        self,
        *,
        prompt_center: PromptCenter,
        decision: RouteDecision,
        context: ConversationContext,
        router_plan: dict[str, Any] | None = None,
    ) -> ResolvedEducationPlan:
        """把当前轮 router plan 转成稳定教育计划。"""
        raw_plan = dict(router_plan or {})
        plan = self._normalize_plan(
            raw_plan,
            context=context,
            decision=decision,
        )
        loader = PromptSkillLoader(prompt_center)
        capability = loader.load_capability("education")
        task = loader.load_task(plan.module)
        knowledge_name = "general-knowledge" if plan.subject == "general" else plan.subject
        knowledge = loader.load_knowledge(knowledge_name)
        method = loader.load_method(plan.pedagogy.replace("_", "-"))

        response_contract = {
            "module": plan.module,
            "pedagogy": plan.pedagogy,
            "answer_boundary": plan.answer_boundary,
        }
        speech_policy = {
            "method": method.name,
            "learner_state": plan.learner_state,
        }
        return ResolvedEducationPlan(
            plan=plan,
            capability=capability,
            task=task,
            knowledge=knowledge,
            method=method,
            response_contract=response_contract,
            speech_policy=speech_policy,
        )

    def _normalize_plan(
        self,
        raw_plan: dict[str, Any],
        *,
        context: ConversationContext,
        decision: RouteDecision,
    ) -> EducationTurnPlan:
        plan = EducationTurnPlan.from_payload(
            raw_plan,
            confidence=decision.confidence,
        )
        learner_state = self._normalize_learner_state(plan, context=context)
        answer_boundary = self._normalize_answer_boundary(plan, learner_state=learner_state)
        return EducationTurnPlan(
            branch=plan.branch,
            module=plan.module,
            subject=plan.subject,
            pedagogy=plan.pedagogy,
            answer_boundary=answer_boundary,
            learner_state=learner_state,
            primary_scenario=plan.primary_scenario,
            primary_action=plan.primary_action,
            learning_objects=plan.learning_objects,
            object_scope=plan.object_scope,
            object_continuity=plan.object_continuity,
            question_kind=plan.question_kind,
            message_block_role=plan.message_block_role,
            prompt_overrides=plan.prompt_overrides,
            secondary_actions=plan.secondary_actions,
            confidence=plan.confidence or decision.confidence,
            plan_reason=plan.plan_reason,
            raw_plan=dict(plan.raw_plan),
        )

    def _normalize_learner_state(
        self,
        plan: EducationTurnPlan,
        *,
        context: ConversationContext,
    ) -> str:
        raw_value = str((plan.raw_plan or {}).get("learner_state") or "").strip()
        candidate = raw_value or str(plan.learner_state or "").strip()
        if raw_value and candidate in self._VALID_LEARNER_STATES:
            return candidate

        text_blocks = [
            str(block.get("text", "") or "").strip().lower()
            for block in list(context.current.user_message.get("content") or [])
            if isinstance(block, dict) and str(block.get("type", "") or "").strip() == "input_text"
        ]
        text = "\n".join(item for item in text_blocks if item).strip()
        if any(token in text for token in ("不会", "不懂", "卡住", "下一步", "怎么做", "stuck", "how do i")):
            return "blocked"
        if any(token in text for token in ("对吗", "对不对", "是不是", "correct", "right?")):
            return "verifying"
        if any(token in text for token in ("什么意思", "为什么", "没听懂", "why", "i don't understand")):
            return "confused"
        return "followup"

    def _normalize_answer_boundary(
        self,
        plan: EducationTurnPlan,
        *,
        learner_state: str,
    ) -> str:
        raw_value = str((plan.raw_plan or {}).get("answer_boundary") or "").strip()
        candidate = raw_value or str(plan.answer_boundary or "").strip()
        if raw_value and candidate in self._VALID_BOUNDARIES:
            return candidate
        if learner_state == "blocked":
            return "hint_first"
        if learner_state == "verifying":
            return "targeted_answer"
        return "direct_explain"
