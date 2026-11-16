"""教育计划解析器。"""

from __future__ import annotations

from dataclasses import dataclass, replace
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

        task_names = set(loader.list_task_names())
        module = plan.module if plan.module in task_names else self._fallback_module(decision, task_names)

        knowledge_names = set(loader.list_knowledge_names())
        subject = self._normalize_subject(plan.subject, knowledge_names)

        method_names = set(loader.list_method_names())
        pedagogy = self._normalize_pedagogy(plan.pedagogy, method_names)

        if (module, subject, pedagogy) != (plan.module, plan.subject, plan.pedagogy):
            plan = replace(plan, module=module, subject=subject, pedagogy=pedagogy)

        task = loader.load_task(module)
        knowledge = loader.load_knowledge(subject)
        method = loader.load_method(pedagogy.replace("_", "-"))

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

    @staticmethod
    def _fallback_module(decision: RouteDecision, task_names: set[str]) -> str:
        """模型给出非法 module（如把学科当任务）时，按意图回退到合法任务。"""
        intent = str(decision.intent or "").lower()
        for token, candidate in (
            ("solve", "solve"),
            ("check", "check"),
            ("correct", "check"),
            ("grade", "check"),
            ("explain", "explain"),
            ("assess", "assess"),
            ("fact", "fact"),
            ("query", "qa"),
            ("qa", "qa"),
        ):
            if token in intent and candidate in task_names:
                return candidate
        for candidate in ("solve", "qa", "answer"):
            if candidate in task_names:
                return candidate
        return next(iter(task_names), "solve")

    _SUBJECT_ALIASES = {
        "algebra": "math", "geometry": "math", "calculus": "math",
        "trigonometry": "math", "arithmetic": "math", "statistics": "math",
        "maths": "math", "mathematics": "math",
        "language": "chinese", "yuwen": "chinese",
        "programming": "cs", "computer": "cs", "coding": "cs",
    }

    @classmethod
    def _normalize_subject(cls, subject: str, knowledge_names: set[str]) -> str:
        value = str(subject or "").strip()
        if value in {"", "general"}:
            return "general-knowledge" if "general-knowledge" in knowledge_names else value
        if value in knowledge_names:
            return value
        alias = cls._SUBJECT_ALIASES.get(value.lower())
        if alias and alias in knowledge_names:
            return alias
        return "general-knowledge" if "general-knowledge" in knowledge_names else value

    @staticmethod
    def _normalize_pedagogy(pedagogy: str, method_names: set[str]) -> str:
        value = str(pedagogy or "").strip() or "step_by_step"
        normalized = value.replace("_", "-")
        if normalized in method_names:
            return value
        if "step-by-step" in method_names:
            return "step_by_step"
        return next(iter(method_names), value).replace("-", "_")

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
