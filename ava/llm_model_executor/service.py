"""LLM 服务入口。"""

from __future__ import annotations

import threading

from ava.llm_model_executor.provider import OpenAIResponsesProvider
from ava.llm_model_executor.request import InferenceRequestBuilder
from ava.llm_model_executor.types import InferenceResult, InferenceTask, ModelRequestContext
from ava.capabilities.prompt.prompt_loader import PromptCenter
from ava.multi_turn_context_builder.compiler import ContextCompiler
from ava.multi_turn_context_builder.types import ConversationBuildOptions, ConversationContext
from ava.domain.conversation.strategy import BranchStrategy
from ava.router_selector.request import RouterRequestBuilder
from configs import settings


class RequestContextBuilder:
    """构建消息优先的模型请求上下文。"""

    def __init__(
        self,
        prompt_center: PromptCenter,
        compiler: ContextCompiler | None = None,
    ) -> None:
        self.prompt_center = prompt_center
        self.compiler = compiler or ContextCompiler()
        self.router_builder = RouterRequestBuilder(self.compiler)

    def build(
        self,
        *,
        task: InferenceTask,
        state,
        turn_input,
        decision=None,
        plan=None,
        history_window: int | None = None,
        max_context_messages: int | None = None,
        current_turn_id: int | None = None,
        context: ConversationContext | None = None,
        metadata: dict | None = None,
    ) -> ModelRequestContext:
        if task == InferenceTask.ROUTE:
            return self._build_route_context(
                state=state,
                turn_input=turn_input,
                history_window=int(history_window or settings.runtime.history_window or 8),
                max_context_messages=max_context_messages,
                current_turn_id=current_turn_id,
                context=context,
                metadata=metadata,
            )
        return self._build_generate_context(
            state=state,
            turn_input=turn_input,
            decision=decision,
            plan=plan,
            history_window=int(history_window or settings.runtime.history_window or 8),
            max_context_messages=max_context_messages,
            current_turn_id=current_turn_id,
            context=context,
            metadata=metadata,
        )

    def _build_route_context(
        self,
        *,
        state,
        turn_input,
        history_window: int,
        max_context_messages: int | None,
        current_turn_id: int | None,
        context: ConversationContext | None,
        metadata: dict | None,
    ) -> ModelRequestContext:
        context = context or self.compiler.build_conversation_context(
            state=state,
            turn_input=turn_input,
            options=ConversationBuildOptions(
                history_window=history_window,
                current_turn_id=current_turn_id,
                max_context_messages=int(
                    max_context_messages
                    or settings.runtime.router_max_context_messages
                    or settings.runtime.max_context_messages
                    or 8
                ),
                profile="router",
            ),
        )

        text_only_router = bool((metadata or {}).get("text_only_router", False))
        selected_model = self.compiler.continuity_policy.select_router_model(
            current_artifacts=context.current.artifacts,
            text_only=text_only_router,
            model=str(
                (metadata or {}).get("model_override")
                or settings.runtime.router_model
                or settings.openai_config.model
                or settings.openai_config.intent_model
            ).strip(),
            multimodal_model=str(
                settings.openai_config.multimodal_model
                or settings.openai_config.model
            ).strip(),
        )
        router_request = self.router_builder.build(
            prompt_center=self.prompt_center,
            state=state,
            turn_input=context.current.turn_input,
            options=ConversationBuildOptions(
                history_window=history_window,
                current_turn_id=current_turn_id,
                max_context_messages=max_context_messages,
                profile=context.session.profile,
            ),
            context=context,
            text_only=text_only_router,
        )
        return ModelRequestContext(
            task=InferenceTask.ROUTE,
            session_id=state.session_id,
            model=selected_model,
            instructions=router_request.instructions,
            messages=router_request.input,
            metadata={
                "state": state,
                "context": context,
                "active_skills": router_request.active_skills,
                "current_turn_id": current_turn_id,
                **dict(metadata or {}),
            },
        )

    def _build_generate_context(
        self,
        *,
        state,
        turn_input,
        decision,
        plan,
        history_window: int,
        max_context_messages: int | None,
        current_turn_id: int | None,
        context: ConversationContext | None,
        metadata: dict | None,
    ) -> ModelRequestContext:
        context = context if isinstance(context, ConversationContext) else None
        context = context or self.compiler.build_conversation_context(
            state=state,
            turn_input=turn_input,
            options=ConversationBuildOptions(
                history_window=history_window,
                current_turn_id=current_turn_id,
                max_context_messages=int(
                    max_context_messages
                    or settings.runtime.responder_max_context_messages
                    or settings.runtime.max_context_messages
                    or 16
                ),
                profile="responder_minimal",
            ),
        )

        strategy = getattr(plan, "strategy", None)
        if not isinstance(strategy, BranchStrategy):
            raise ValueError("Generate context is missing plan.strategy for prompt resolution.")

        compiled_payload = self.compiler.compile_responder_payload(
            prompt_center=self.prompt_center,
            context=context,
            strategy=strategy,
            decision=decision,
        )
        selected_model = str(
            (metadata or {}).get("model_override")
            or settings.openai_config.multimodal_model
            or settings.openai_config.model
        ).strip()
        return ModelRequestContext(
            task=InferenceTask.GENERATE,
            session_id=state.session_id,
            model=selected_model,
            instructions=compiled_payload.instructions,
            messages=list(compiled_payload.input),
            metadata={
                "state": state,
                "context": context,
                "decision": decision,
                "plan": plan,
                "strategy": strategy.to_metadata(),
                "active_skills": compiled_payload.active_skills,
                "current_turn_id": current_turn_id,
                **dict(metadata or {}),
            },
        )


class LLMService:
    """统一的 LLM 执行服务。"""

    def __init__(
        self,
        *,
        prompt_center: PromptCenter,
        provider: OpenAIResponsesProvider | None = None,
        request_builder: InferenceRequestBuilder | None = None,
        context_compiler: ContextCompiler | None = None,
        context_builder: RequestContextBuilder | None = None,
    ) -> None:
        self.prompt_center = prompt_center
        self.context_compiler = context_compiler or ContextCompiler()
        self.context_builder = context_builder or RequestContextBuilder(
            prompt_center,
            compiler=self.context_compiler,
        )
        self.provider = provider or OpenAIResponsesProvider.from_settings()
        self.request_builder = request_builder or InferenceRequestBuilder()

    def build_context(self, **kwargs) -> ModelRequestContext:
        return self.context_builder.build(**kwargs)

    def route(self, context: ModelRequestContext) -> InferenceResult:
        return self._execute(context)

    def generate(self, context: ModelRequestContext) -> InferenceResult:
        return self._execute(context)

    def stream_generate(
        self,
        context: ModelRequestContext,
        *,
        stop_event: threading.Event | None = None,
    ):
        provider = self._provider_for_context(context)
        stream_request = self._build_request(context, stream=True)
        yield from provider.stream(stream_request, stop_event=stop_event)

    def _build_request(self, context: ModelRequestContext, *, stream: bool = False):
        request = self.request_builder.build(context)
        if not stream:
            return request
        return type(request)(**{**request.__dict__, "stream": True})

    def _execute(self, context: ModelRequestContext) -> InferenceResult:
        request = self._build_request(context)
        provider = self._provider_for_context(context)
        return provider.chat(request)

    def _provider_for_context(self, context: ModelRequestContext) -> OpenAIResponsesProvider:
        api_base = str((context.metadata or {}).get("api_base", "") or "").strip()
        api_key = str((context.metadata or {}).get("api_key", "") or "").strip()
        if api_base and api_key:
            return OpenAIResponsesProvider(api_base=api_base, api_key=api_key)
        return self.provider
