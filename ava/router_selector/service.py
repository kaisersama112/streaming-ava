"""路由选择主实现。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from ava.capabilities.prompt import PromptCenter
from ava.domain.conversation.state import ConversationState
from ava.llm_model_executor import InferenceTask, LLMService, ModelRequestContext
from ava.multi_turn_context_builder import ContextCompiler, ConversationBuildOptions, ConversationContext

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
