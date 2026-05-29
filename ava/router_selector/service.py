"""路由服务。"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from typing import Any

from ava.llm_model_executor.service import LLMService
from ava.llm_model_executor.types import InferenceTask
from ava.capabilities.prompt import PromptCenter
from ava.multi_turn_context_builder.compiler import ContextCompiler
from ava.multi_turn_context_builder.types import ContextSession, ConversationBuildOptions, ConversationContext
from ava.domain.conversation.state import ConversationState
from ava.domain.multimodal import TurnInput
from configs import settings

from .policy import RouterDecisionPolicy
from .schema import RouteDecision


@dataclass(frozen=True)
class RouterResult:
    """返回给后续流水线的最终路由结果。"""

    decision: RouteDecision
    context: ConversationContext
    router_plan: dict[str, Any]
    artifact_brief: dict[str, Any]
    selection_summary: dict[str, Any]


@dataclass(frozen=True)
class _PreparedContext:
    """内部使用的路由上下文。"""

    base_context: ConversationContext
    route_context: ConversationContext
    isolated: bool


@dataclass(frozen=True)
class _ExecutionConfig:
    """路由执行配置。"""

    api_base: str
    api_key: str
    timeout: int | None
    selected_model_name: str
    selected_multimodal_model: str
    chosen_model: str
    text_only_router: bool
    artifact_brief: dict[str, Any]


@dataclass(frozen=True)
class _ParsedRouterResponse:
    """解析后的路由模型输出。"""

    decision: RouteDecision
    plan: dict[str, Any]


class RouterService:
    """协调一次完整的路由流程。"""

    def __init__(
        self,
        *,
        prompt_center: PromptCenter,
        compiler: ContextCompiler | None = None,
        policy: RouterDecisionPolicy | None = None,
    ) -> None:
        self.prompt_center = prompt_center
        self.compiler = compiler or ContextCompiler()
        self.policy = policy or RouterDecisionPolicy()

    def route(
        self,
        *,
        turn_input: TurnInput | str,
        state: ConversationState,
        history_window: int,
        max_context_messages: int | None = None,
        current_turn_id: int | None = None,
        context: ConversationContext | None = None,
        api_base: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        multimodal_model: str | None = None,
        timeout: int | None = None,
    ) -> RouterResult:
        prepared = self._prepare_context(
            state=state,
            turn_input=turn_input,
            history_window=history_window,
            max_context_messages=max_context_messages,
            current_turn_id=current_turn_id,
            context=context,
        )
        execution = self._plan_execution(
            state=state,
            prepared=prepared,
            api_base=api_base,
            api_key=api_key,
            model=model,
            multimodal_model=multimodal_model,
            timeout=timeout,
        )

        llm_service = LLMService(
            prompt_center=self.prompt_center,
            context_compiler=self.compiler,
        )
        request_context = llm_service.build_context(
            task=InferenceTask.ROUTE,
            state=state,
            turn_input=prepared.route_context.current.turn_input,
            history_window=history_window,
            max_context_messages=max_context_messages,
            current_turn_id=current_turn_id,
            context=prepared.route_context,
            metadata={
                "api_base": execution.api_base,
                "api_key": execution.api_key,
                "timeout": execution.timeout,
                "model_override": execution.chosen_model,
                "text_only_router": execution.text_only_router,
            },
        )

        raw = llm_service.route(request_context).text
        parsed = self._parse_response(raw)
        result = self._finalize_result(
            parsed=parsed,
            prepared=prepared,
            artifact_brief=execution.artifact_brief,
            session_id=state.session_id,
            current_turn_id=current_turn_id,
            selected_model_name=execution.selected_model_name,
        )
        print("[router-selection]", json.dumps(result.selection_summary, ensure_ascii=False))
        return result

    def _prepare_context(
        self,
        *,
        state: ConversationState,
        turn_input: TurnInput | str,
        history_window: int,
        max_context_messages: int | None = None,
        current_turn_id: int | None = None,
        context: ConversationContext | None = None,
    ) -> _PreparedContext:
        base_context = context or self.compiler.build_conversation_context(
            state=state,
            turn_input=turn_input,
            options=ConversationBuildOptions(
                history_window=history_window,
                current_turn_id=current_turn_id,
                max_context_messages=max_context_messages,
                profile="router",
            ),
        )
        isolated = self.compiler.continuity_policy.should_isolate_current_artifact_context(
            state,
            base_context,
            current_turn_id=current_turn_id,
        )
        route_context = base_context
        if isolated:
            route_context = replace(
                base_context,
                session=ContextSession(
                    session_id=base_context.session.session_id,
                    session_scene="general",
                    turn_scene="general_qa",
                    profile=base_context.session.profile,
                ),
                conversation=[],
            )
        return _PreparedContext(
            base_context=base_context,
            route_context=route_context,
            isolated=isolated,
        )

    def _plan_execution(
        self,
        *,
        state: ConversationState,
        prepared: _PreparedContext,
        api_base: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        multimodal_model: str | None = None,
        timeout: int | None = None,
    ) -> _ExecutionConfig:
        route_context = prepared.route_context
        selected_api_base = api_base or settings.openai_config.api_base
        selected_api_key = api_key or settings.openai_config.api_key
        selected_model_name = (
            model
            or settings.runtime.router_model
            or settings.openai_config.model
            or settings.openai_config.intent_model
        )
        selected_multimodal_model = str(
            multimodal_model
            or settings.openai_config.multimodal_model
            or selected_model_name
        ).strip() or selected_model_name
        selected_timeout = timeout or settings.runtime.router_timeout

        artifact_brief = self.compiler.continuity_policy.build_artifact_brief_for_turn(
            state,
            current_artifacts=route_context.current.artifacts,
        )
        artifact_brief_source = str(artifact_brief.get("source") or "").strip()
        text_only_router = artifact_brief_source in {"turn_result", "llm_brief"}
        chosen_model = self.compiler.continuity_policy.select_router_model(
            current_artifacts=route_context.current.artifacts,
            text_only=text_only_router,
            model=selected_model_name,
            multimodal_model=selected_multimodal_model,
        )
        return _ExecutionConfig(
            api_base=selected_api_base,
            api_key=selected_api_key,
            timeout=selected_timeout,
            selected_model_name=selected_model_name,
            selected_multimodal_model=selected_multimodal_model,
            chosen_model=chosen_model,
            text_only_router=text_only_router,
            artifact_brief=artifact_brief,
        )

    def _parse_response(self, raw: str) -> _ParsedRouterResponse:
        obj = self._extract_json_object(raw)
        decision_payload = {key: value for key, value in obj.items() if key != "plan"}
        decision = RouteDecision.model_validate(decision_payload)
        plan = self._normalize_plan(
            decision=decision,
            plan_payload=obj.get("plan"),
        )
        return _ParsedRouterResponse(decision=decision, plan=plan)

    def _normalize_plan(
        self,
        *,
        decision: RouteDecision,
        plan_payload: Any,
    ) -> dict[str, Any]:
        if isinstance(plan_payload, dict):
            plan = dict(plan_payload)
            if plan:
                return plan
        return self._build_fallback_plan(decision)

    @staticmethod
    def _build_fallback_plan(decision: RouteDecision) -> dict[str, Any]:
        if decision.turn_scene == "education":
            return {
                "module": "solve",
                "subject": "general",
                "pedagogy": "step_by_step",
                "policy_id": "",
                "primary_scenario": "practice",
                "primary_action": "solve_current_problem",
                "learning_objects": ["problem"],
                "object_scope": "whole_problem",
                "object_continuity": "uncertain",
                "answer_boundary": "direct_explain",
                "plan_reason": "router_plan_missing_fallback",
                "confidence": decision.confidence,
            }

        fallback_mode = {
            "general_qa": "fact",
            "casual_chat": "smalltalk",
            "clarify": "subject",
        }.get(decision.turn_scene, "fact")
        return {
            "mode": fallback_mode,
            "plan_reason": "router_plan_missing_fallback",
            "confidence": decision.confidence,
        }

    def _extract_json_object(self, text: str) -> dict[str, Any]:
        value = text.strip()
        if not value:
            raise ValueError("empty router output")

        try:
            return json.loads(value)
        except json.JSONDecodeError:
            pass

        start = value.find("{")
        end = value.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("json object not found")
        return json.loads(value[start: end + 1])

    def _finalize_result(
        self,
        *,
        parsed: _ParsedRouterResponse,
        prepared: _PreparedContext,
        artifact_brief: dict[str, Any],
        session_id: str,
        current_turn_id: int | None,
        selected_model_name: str,
    ) -> RouterResult:
        final_decision = self.policy.apply(
            parsed.decision,
            current_session_scene=prepared.route_context.session.session_scene,
        )
        selection_summary = {
            "session_id": session_id,
            "turn_id": current_turn_id,
            "model": selected_model_name,
            "session_scene": final_decision.session_scene,
            "turn_scene": final_decision.turn_scene,
            "intent": final_decision.intent,
            "confidence": final_decision.confidence,
            "need_clarification": final_decision.need_clarification,
            "should_preserve_teaching_state": final_decision.should_preserve_teaching_state,
            "router_plan": parsed.plan,
        }
        return RouterResult(
            decision=final_decision,
            context=prepared.route_context,
            router_plan=parsed.plan,
            artifact_brief=artifact_brief,
            selection_summary=selection_summary,
        )
