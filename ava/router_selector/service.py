"""路由选择主实现。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from ava.capabilities.prompt import build_responder_prompt_package
from ava.capabilities.prompt.prompt_loader import PromptCenter
from ava.domain.conversation.state import ConversationState
from ava.inference_runtime.types import (
    TurnPlan,
    TurnPlanDebug,
    TurnPlanExecution,
    TurnPlanPayload,
    TurnPlanRuntimeContext,
)
from ava.llm_model_executor.service import LLMService
from ava.llm_model_executor.types import InferenceTask, ModelRequestContext
from ava.multi_turn_context_builder import ContextCompiler, ConversationBuildOptions, ConversationContext
from ava.router_selector.strategy_builder import build_strategy_from_model_plan

from .schema import RouteDecision


@dataclass(frozen=True)
class RouterRequestArtifacts:
    """路由模型请求载荷。"""

    context: ConversationContext
    instructions: str
    input: list[dict[str, object]]
    active_skills: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RouterResult:
    """当前轮路由输出。"""

    decision: RouteDecision
    context: ConversationContext
    router_plan: dict[str, Any]
    request_payload: dict[str, Any]
    raw_output: str
    selection_summary: dict[str, Any]


@dataclass(frozen=True)
class PreparedTurn:
    """已完成路由与计划构建、但尚未进入最终回复执行的单轮结果。"""

    route_result: RouterResult
    turn_plan: TurnPlan


class RouterDecisionPolicy:
    """对模型原始路由输出做最小治理。"""

    @staticmethod
    def _clarify(current_session_scene: str) -> RouteDecision:
        return RouteDecision(
            session_scene="education" if current_session_scene == "education" else "general",
            turn_scene="clarify",
            intent="clarify",
            confidence=0.0,
            should_preserve_teaching_state=(current_session_scene == "education"),
            need_clarification=True,
        )

    def apply(
            self,
            decision: RouteDecision,
            *,
            current_session_scene: str,
    ) -> RouteDecision:
        normalized = RouteDecision.model_validate(decision.model_dump())
        if normalized.turn_scene == "education":
            normalized.session_scene = "education"
            normalized.should_preserve_teaching_state = True
            return normalized
        if normalized.turn_scene == "clarify":
            return normalized
        if normalized.need_clarification:
            return self._clarify(current_session_scene)
        if current_session_scene == "education" and normalized.turn_scene in {"general_qa", "casual_chat"}:
            normalized.session_scene = "education"
            normalized.should_preserve_teaching_state = True
        return normalized


class RouterService:
    """独立路由器。

    统一负责：
    - 构造路由上下文
    - 组装路由请求
    - 调用模型
    - 解析与治理路由结果
    """

    def __init__(
            self,
            *,
            prompt_center: PromptCenter,
            context_compiler: ContextCompiler | None = None,
            llm_service: LLMService | None = None,
            policy: RouterDecisionPolicy | None = None,
    ) -> None:
        self.prompt_center = prompt_center
        self.context_compiler = context_compiler or ContextCompiler()
        self.llm_service = llm_service or LLMService()
        self.policy = policy or RouterDecisionPolicy()

    @staticmethod
    def _extract_json_object(text: str) -> dict[str, Any]:
        value = str(text or "").strip()
        if not value:
            raise ValueError("empty router output")
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            start = value.find("{")
            end = value.rfind("}")
            if start == -1 or end == -1 or end <= start:
                raise
            return json.loads(value[start: end + 1])

    def _prepare_context(
            self,
            *,
            state: ConversationState,
            user_message: dict[str, Any],
            history_window: int,
            max_context_messages: int | None = None,
            current_turn_id: int | None = None,
            context: ConversationContext | None = None,
    ) -> ConversationContext:
        return context or self.context_compiler.build_conversation_context(
            state=state,
            user_message=user_message,
            options=ConversationBuildOptions(
                history_window=history_window,
                current_turn_id=current_turn_id,
                max_context_messages=max_context_messages,
                profile="router",
            ),
        )

    def _build_request(
            self,
            *,
            state: ConversationState,
            user_message: dict[str, Any],
            history_window: int,
            max_context_messages: int | None = None,
            current_turn_id: int | None = None,
            context: ConversationContext | None = None,
    ) -> RouterRequestArtifacts:
        current_context = context or self.context_compiler.build_conversation_context(
            state=state,
            user_message=user_message,
            options=ConversationBuildOptions(
                history_window=history_window,
                current_turn_id=current_turn_id,
                max_context_messages=max_context_messages,
                profile="router",
            ),
        )
        payload = self.context_compiler.compile_router_payload(
            prompt_center=self.prompt_center,
            context=current_context,
        )
        return RouterRequestArtifacts(
            context=current_context,
            instructions=payload.instructions,
            input=list(payload.input),
            active_skills=list(payload.active_skills),
            metadata={
                "profile": current_context.session.profile,
                "sections": dict(payload.sections or {}),
            },
        )

    def route(
            self,
            *,
            user_message: dict[str, Any],
            state: ConversationState,
            history_window: int,
            max_context_messages: int | None = None,
            current_turn_id: int | None = None,
            context: ConversationContext | None = None,
            model: str = "",
            timeout: int | None = None,
            api_base: str = "",
            api_key: str = "",
    ) -> RouterResult:
        route_context = self._prepare_context(
            state=state,
            user_message=user_message,
            history_window=history_window,
            max_context_messages=max_context_messages,
            current_turn_id=current_turn_id,
            context=context,
        )
        request = self._build_request(
            state=state,
            user_message=user_message,
            history_window=history_window,
            max_context_messages=max_context_messages,
            current_turn_id=current_turn_id,
            context=route_context,
        )
        request_context = ModelRequestContext(
            task=InferenceTask.ROUTE,
            session_id=state.session_id,
            model=str(model or "").strip() or "router-model",
            instructions=request.instructions,
            input=list(request.input),
            metadata={
                "timeout": timeout,
                "api_base": api_base,
                "api_key": api_key,
            },
        )
        result = self.llm_service.route(request_context)
        raw_output = str(result.text or "")
        parsed = self._extract_json_object(raw_output)
        decision = RouteDecision.model_validate({key: value for key, value in parsed.items() if key != "plan"})
        final_decision = self.policy.apply(
            decision,
            current_session_scene=route_context.session.session_scene,
        )
        router_plan = dict(parsed.get("plan") or {})
        selection_summary = {
            "session_id": state.session_id,
            "turn_id": current_turn_id,
            "session_scene": final_decision.session_scene,
            "turn_scene": final_decision.turn_scene,
            "intent": final_decision.intent,
            "confidence": final_decision.confidence,
            "router_plan": router_plan,
        }
        return RouterResult(
            decision=final_decision,
            context=route_context,
            router_plan=router_plan,
            request_payload={"instructions": request.instructions, "input": list(request.input)},
            raw_output=raw_output,
            selection_summary=selection_summary,
        )

    def build_turn_plan(
            self,
            *,
            prompt_center: PromptCenter,
            state: ConversationState,
            user_message: dict[str, Any],
            decision: RouteDecision,
            history_window: int,
            max_context_messages: int | None = None,
            context: ConversationContext | None = None,
            current_turn_id: int | None = None,
            strategy: Any | None = None,
            router_plan: dict[str, Any] | None = None,
            model: str = "",
    ) -> TurnPlan:
        selected_strategy = strategy
        if selected_strategy is None:
            selected_strategy = build_strategy_from_model_plan(
                prompt_center,
                decision,
                context,
                router_plan=dict(router_plan or {}),
            )
        selected_prompt_package = getattr(selected_strategy, "prompt_package", None)
        if selected_prompt_package is None:
            selected_prompt_package = build_responder_prompt_package(
                prompt_center=prompt_center,
                strategy=selected_strategy,
            )
        payload = self.context_compiler.compile_responder_payload(
            prompt_center=prompt_center,
            context=context,
            strategy=selected_strategy,
            decision=decision,
        )
        active_skill_names = list(selected_prompt_package.skill_names())
        return TurnPlan(
            decision=decision,
            strategy=selected_strategy,
            prompt_package=selected_prompt_package,
            payload=TurnPlanPayload(
                instructions=payload.instructions,
                input=list(payload.input),
            ),
            execution=TurnPlanExecution(
                orchestrator_name="Router Prepared Turn Builder",
                model=str(model or "").strip(),
            ),
            runtime_context=TurnPlanRuntimeContext(
                conversation_context=context,
            ),
            debug=TurnPlanDebug(
                router_plan=dict(router_plan or {}),
                active_skills=active_skill_names,
                prompt_package=selected_prompt_package.to_metadata(),
            ),
        )

    def prepare_turn(
            self,
            *,
            prompt_center: PromptCenter,
            state: ConversationState,
            user_message: dict[str, Any],
            history_window: int,
            max_context_messages: int | None = None,
            current_turn_id: int | None = None,
            router_model: str = "",
            responder_model: str = "",
            timeout: int | None = None,
            api_base: str = "",
            api_key: str = "",
            strategy: Any | None = None,
    ) -> PreparedTurn:
        # 意图识别
        route_result = self.route(
            user_message=user_message,
            state=state,
            history_window=history_window,
            max_context_messages=max_context_messages,
            current_turn_id=current_turn_id,
            model=router_model,
            timeout=timeout,
            api_base=api_base,
            api_key=api_key,
        )
        # 路由选取
        turn_plan = self.build_turn_plan(
            prompt_center=prompt_center,
            state=state,
            user_message=user_message,
            decision=route_result.decision,
            history_window=history_window,
            max_context_messages=max_context_messages,
            context=route_result.context,
            current_turn_id=current_turn_id,
            strategy=strategy,
            router_plan=route_result.router_plan,
            model=responder_model,
        )
        return PreparedTurn(
            route_result=route_result,
            turn_plan=turn_plan,
        )
