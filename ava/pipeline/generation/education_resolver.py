"""教育领域计划解析器。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ava.capabilities.prompt.education_catalog import EducationPromptAssets, EducationPromptCatalog
from ava.capabilities.prompt.prompt_loader import PromptCenter
from ava.domain.memory.message import user_message_text
from ava.multi_turn_context_builder.types import ConversationContext
from ava.pipeline.generation.education_plan import EducationTurnPlan
from ava.router_selector.schema import RouteDecision


@dataclass(frozen=True)
class ResolvedEducationPlan:
    """
    解析后的教育计划。

    它是 `router_plan` 和最终 `BranchStrategy` 之间的中间层：
    - plan 负责表达这轮教学意图；
    - assets 负责表达本轮要装配哪些稳定提示资产；
    - 其余字段负责把输出模式、UI 等派生结果固定下来。
    """

    plan: EducationTurnPlan
    assets: EducationPromptAssets
    delivery_mode: str
    ui_mode: str
    response_contract: dict[str, Any]
    speech_policy: dict[str, Any]


class EducationPlanResolver:
    """把 router 的原始教育计划归一化为可执行计划。"""

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
        """
        把当前轮的 router 计划变成稳定教育计划。

        这里承担两类职责：
        1. 校验 / 修正 router 输出；
        2. 决定本轮需要加载哪些教育 prompt 资产。
        """
        raw_plan = dict(router_plan or {})
        plan = self._normalize_plan(
            raw_plan,
            context=context,
            decision=decision,
        )
        catalog = EducationPromptCatalog(prompt_center)
        assets = catalog.load_assets(
            module=plan.module,
            subject=plan.subject,
            pedagogy=plan.pedagogy,
        )

        module_defaults = dict(assets.module.output_defaults or {})
        pedagogy_adjustments = dict(assets.pedagogy.output_adjustments or {})
        delivery_mode = str(module_defaults.get("delivery_mode") or "speech_ui_dual").strip() or "speech_ui_dual"
        ui_mode = self._select_ui_mode(
            plan=plan,
            module_defaults=module_defaults,
            subject_ui_hints=dict(assets.subject.ui_hints or {}),
        )
        response_contract = {
            "module": plan.module,
            "pedagogy": plan.pedagogy,
            "answer_boundary": plan.answer_boundary,
            **module_defaults,
            **pedagogy_adjustments,
        }
        speech_policy = {
            "tone": assets.pedagogy.tone,
            "policy_id": plan.policy_id,
            "learner_state": plan.learner_state,
        }
        return ResolvedEducationPlan(
            plan=plan,
            assets=assets,
            delivery_mode=delivery_mode,
            ui_mode=ui_mode,
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
        """补齐教育计划默认值，并把 router 的旧字段名统一到新语义。"""
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
            artifact_role=plan.artifact_role,
            ui_mode_hint=plan.ui_mode_hint,
            policy_id=plan.policy_id,
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
        """
        归一化学生状态。

        当前先使用轻量规则补默认值，后续可把这部分迁到 router
        的显式 schema 中，进一步减少本地推断。
        """
        raw_value = str((plan.raw_plan or {}).get("learner_state") or "").strip()
        candidate = raw_value or str(plan.learner_state or "").strip()
        if raw_value and candidate in self._VALID_LEARNER_STATES:
            return candidate

        user_text = user_message_text(context.current.user_message).strip().lower()
        if any(token in user_text for token in ("不会", "不懂", "卡住", "下一步", "怎么做")):
            return "blocked"
        if any(token in user_text for token in ("stuck", "next step", "how do i", "how to do", "can't do")):
            return "blocked"
        if any(token in user_text for token in ("对吗", "对不对", "是不是", "我这样写")):
            return "verifying"
        if any(token in user_text for token in ("is this right", "am i right", "correct", "right?")):
            return "verifying"
        if any(token in user_text for token in ("什么意思", "为什么", "没听懂", "没明白")):
            return "confused"
        if any(token in user_text for token in ("why", "what does it mean", "i don't understand")):
            return "confused"
        return "followup"

    def _normalize_answer_boundary(
        self,
        plan: EducationTurnPlan,
        *,
        learner_state: str,
    ) -> str:
        """根据学生状态与已有计划修正回答边界。"""
        raw_value = str((plan.raw_plan or {}).get("answer_boundary") or "").strip()
        candidate = raw_value or str(plan.answer_boundary or "").strip()
        if raw_value and candidate in self._VALID_BOUNDARIES:
            return candidate
        if learner_state == "blocked":
            return "hint_first"
        if learner_state == "verifying":
            return "targeted_answer"
        if learner_state == "confused":
            return "direct_explain"
        return "direct_explain"

    @staticmethod
    def _select_ui_mode(
        *,
        plan: EducationTurnPlan,
        module_defaults: dict[str, Any],
        subject_ui_hints: dict[str, Any],
    ) -> str:
        """根据计划、模块默认值和学科提示选择 UI 模式。"""
        if str(plan.ui_mode_hint or "").strip():
            return str(plan.ui_mode_hint).strip()
        module_ui_mode = str(module_defaults.get("ui_mode", "") or "").strip()
        if module_ui_mode == "none":
            return "none"
        return str(subject_ui_hints.get("ui_mode_default", "") or module_ui_mode or "learning_card").strip()
