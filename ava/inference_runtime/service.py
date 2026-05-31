"""推理运行时主实现。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from ava.capabilities.prompt import PromptCenter
from ava.domain.conversation.state import ConversationState
from ava.llm_model_executor import (
    InferenceCompleted,
    InferenceError,
    InferenceTask,
    LLMService,
    OutputTextDelta,
    ModelRequestContext,
)
from ava.multi_turn_context_builder import ContextCompiler, ConversationBuildOptions, ConversationContext
from ava.router_selector import RouterService

from .types import TurnPlan


@dataclass
class ReplyExecutionResult:
    """回复执行结果。"""

    assistant_text: str
    backend: str
    debug: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class InferenceRuntimeResult:
    """单轮推理运行结果。"""

    route_result: Any
    turn_plan: TurnPlan
    reply_result: ReplyExecutionResult


class ReplyService:
    """把执行计划真正送入模型执行器。"""

    def __init__(
            self,
            *,
            llm_service: LLMService | None = None
    ) -> None:
        self.llm_service = llm_service or LLMService()

    def generate(
            self,
            *,
            session_id: str,
            plan: TurnPlan,
            model: str,
            metadata: dict[str, Any] | None = None,
    ) -> ReplyExecutionResult:

        context = ModelRequestContext(
            task=InferenceTask.GENERATE,
            session_id=session_id,
            model=str(model or plan.model or "").strip() or "response-model",
            instructions=plan.instructions,
            input=list(plan.input),
            metadata=dict(metadata or {}),
        )
        result = self.llm_service.generate(context)
        return ReplyExecutionResult(
            assistant_text=result.text,
            backend="llm_responses",
            debug={"response_metadata": dict(result.metadata or {})},
        )

    def stream(
            self,
            *,
            session_id: str,
            plan: TurnPlan,
            model: str,
            on_token: Callable[[str], None],
            metadata: dict[str, Any] | None = None,
            stop_event=None,
    ) -> ReplyExecutionResult:

        context = ModelRequestContext(
            task=InferenceTask.GENERATE,
            session_id=session_id,
            model=str(model or plan.model or "").strip() or "response-model",
            instructions=plan.instructions,
            input=list(plan.input),
            metadata=dict(metadata or {}),
        )
        parts: list[str] = []
        final_metadata: dict[str, Any] = {}
        for event in self.llm_service.stream_generate(context, stop_event=stop_event):
            if isinstance(event, OutputTextDelta):
                parts.append(event.text)
                on_token(event.text)
            elif isinstance(event, InferenceCompleted):
                final_metadata = dict(event.metadata or {})
            elif isinstance(event, InferenceError):
                raise RuntimeError(event.error)
        return ReplyExecutionResult(
            assistant_text="".join(parts),
            backend="llm_responses_stream",
            debug={"response_metadata": final_metadata},
        )


class InferenceRuntime:
    """独立运行时。

    统一负责：
    - 调用路由模块
    - 构建当前轮执行计划
    - 触发最终回复执行
    """

    def __init__(
            self,
            *,
            prompt_center: PromptCenter,
            context_compiler: ContextCompiler | None = None,
            llm_service: LLMService | None = None,
            router_service: RouterService | None = None,
            reply_service: ReplyService | None = None,
    ) -> None:
        self.prompt_center = prompt_center
        self.context_compiler = context_compiler or ContextCompiler()
        self.llm_service = llm_service or LLMService()
        self.router_service = router_service or RouterService(
            prompt_center=prompt_center,
            context_compiler=self.context_compiler,
            llm_service=self.llm_service,
        )
        self.reply_service = reply_service or ReplyService(
            llm_service=self.llm_service,
        )

    def build_turn_plan(
            self,
            *,
            state: ConversationState,
            user_message: dict[str, Any],
            decision: Any,
            history_window: int,
            max_context_messages: int | None = None,
            context: ConversationContext | None = None,
            current_turn_id: int | None = None,
            strategy: Any | None = None,
            router_plan: dict[str, Any] | None = None,
            model: str = "",
    ) -> TurnPlan:
        """构造当前轮执行计划。"""

        responder_context = context or self.context_compiler.build_conversation_context(
            state=state,
            user_message=user_message,
            options=ConversationBuildOptions(
                history_window=history_window,
                current_turn_id=current_turn_id,
                max_context_messages=max_context_messages,
                profile="responder",
            ),
        )
        payload = self.context_compiler.compile_responder_payload(
            prompt_center=self.prompt_center,
            context=responder_context,
            strategy=strategy,
            decision=decision,
        )
        return TurnPlan(
            decision=decision,
            orchestrator_name="Independent Inference Runtime",
            strategy=strategy,
            instructions=payload.instructions,
            input=list(payload.input),
            model=str(model or "").strip(),
            router_plan=dict(router_plan or {}),
            metadata={
                "context": responder_context,
                "sections": dict(payload.sections or {}),
                "active_skills": list(payload.active_skills),
            },
        )

    def run_turn(
            self,
            *,
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
    ) -> InferenceRuntimeResult:
        route_result = self.router_service.route(
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
        plan = self.build_turn_plan(
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
        reply_result = self.reply_service.generate(
            session_id=state.session_id,
            plan=plan,
            model=responder_model,
            metadata={"api_base": api_base, "api_key": api_key, "timeout": timeout},
        )
        return InferenceRuntimeResult(
            route_result=route_result,
            turn_plan=plan,
            reply_result=reply_result,
        )


def build_turn_plan(
        state: ConversationState,
        user_message: dict[str, Any],
        decision: Any,
        prompt_center: PromptCenter,
        history_window: int,
        max_context_messages: int | None = None,
        context: ConversationContext | None = None,
        current_turn_id: int | None = None,
        compiler: ContextCompiler | None = None,
        strategy: Any | None = None,
        router_plan: dict[str, Any] | None = None,
        model: str = "",
) -> TurnPlan:
    """兼容函数入口：构造当前轮执行计划。"""

    runtime = InferenceRuntime(
        prompt_center=prompt_center,
        context_compiler=compiler,
    )
    return runtime.build_turn_plan(
        state=state,
        user_message=user_message,
        decision=decision,
        history_window=history_window,
        max_context_messages=max_context_messages,
        context=context,
        current_turn_id=current_turn_id,
        strategy=strategy,
        router_plan=router_plan,
        model=model,
    )


def generate_reply_sync(
        *,
        state,
        turn_input,
        decision,
        plan: TurnPlan,
        context,
        api_base: str,
        api_key: str,
        model: str,
        timeout: int,
        current_turn_id: int | None = None,
) -> ReplyExecutionResult:
    """兼容函数入口：同步生成回复。"""

    del state, turn_input, decision, context, current_turn_id
    service = ReplyService()
    return service.generate(
        session_id="runtime",
        plan=plan,
        model=model,
        metadata={"api_base": api_base, "api_key": api_key, "timeout": timeout},
    )


def stream_reply_with_callbacks(
        *,
        state,
        turn_input,
        decision,
        plan: TurnPlan,
        context,
        api_base: str,
        api_key: str,
        model: str,
        timeout: int,
        on_token,
        current_turn_id: int | None = None,
        stop_event=None,
) -> ReplyExecutionResult:
    """兼容函数入口：流式生成回复。"""

    del state, turn_input, decision, context, current_turn_id
    service = ReplyService()
    return service.stream(
        session_id="runtime",
        plan=plan,
        model=model,
        on_token=on_token,
        metadata={"api_base": api_base, "api_key": api_key, "timeout": timeout},
        stop_event=stop_event,
    )
