import threading

from ava.context_engine.compiler import ContextCompiler
from ava.context_engine.continuity import (
    select_router_model,
    should_isolate_current_artifact_context,
)
from ava.context_engine.types import ContextSnapshot, SnapshotCompileOptions
from ava.capabilities.llm.providers.openai_chat import OpenAIChatProvider
from ava.capabilities.llm.requests.builder import InferenceRequestBuilder
from ava.capabilities.llm.types import InferenceResult, InferenceTask, LLMContext
from ava.capabilities.prompt.prompt_loader import PromptCenter
from configs import settings
from dataclasses import replace


class LLMService:
    def __init__(
        self,
        *,
        prompt_center: PromptCenter,
        provider: OpenAIChatProvider | None = None,
        request_builder: InferenceRequestBuilder | None = None,
        context_compiler: ContextCompiler | None = None,
    ) -> None:
        self.prompt_center = prompt_center
        self.provider = provider or OpenAIChatProvider.from_settings()
        self.context_compiler = context_compiler or ContextCompiler()
        self.request_builder = request_builder or InferenceRequestBuilder(
            prompt_center,
            compiler=self.context_compiler,
        )

    def build_context(
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
        visible_context=None,
        metadata: dict | None = None,
    ) -> LLMContext:
        resolved_history_window = int(history_window or settings.runtime.history_window or 8)
        context: LLMContext
        if task == InferenceTask.ROUTE:
            base_visible_context = visible_context or self.context_compiler.build_snapshot(
                state=state,
                turn_input=turn_input,
                options=SnapshotCompileOptions(
                    history_window=resolved_history_window,
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
            isolate = should_isolate_current_artifact_context(
                state,
                base_visible_context,
                current_turn_id=current_turn_id,
            )
            route_visible_context = base_visible_context
            if isolate:
                route_visible_context = replace(
                    base_visible_context,
                    session_scene="general",
                    turn_scene="general_qa",
                    history_messages=[],
                    turn_records=[],
                )

            artifact_brief = dict(getattr(route_visible_context, "router_artifact_brief", {}) or {})
            artifact_brief_source = str(artifact_brief.get("source") or "").strip()
            text_only_router = artifact_brief_source in {"turn_result", "llm_brief"}
            chosen_model = select_router_model(
                route_visible_context,
                text_only=text_only_router,
                model=str(
                    settings.runtime.router_model
                    or settings.openai_config.model
                    or settings.openai_config.intent_model
                ).strip(),
                multimodal_model=str(
                    settings.openai_config.multimodal_model
                    or settings.openai_config.model
                ).strip(),
            )
            context = LLMContext(
                task=task,
                session_id=state.session_id,
                current_input=route_visible_context.turn_input,
                history=list(route_visible_context.history_messages),
                memory=dict(route_visible_context.memory_projection or {}),
                multimodal={
                    "artifacts_count": len(route_visible_context.artifacts),
                    "reference_artifacts_count": len(route_visible_context.reference_artifacts),
                    "reference_artifacts_inherited": bool(route_visible_context.reference_artifacts_inherited),
                    "router_artifact_brief": dict(route_visible_context.router_artifact_brief or {}),
                },
                routing={
                    "session_scene": route_visible_context.session_scene,
                    "turn_scene": route_visible_context.turn_scene,
                    "artifact_brief_source": artifact_brief_source,
                    "text_only_router": text_only_router,
                    "chosen_model": chosen_model,
                    "isolated": isolate,
                },
                metadata={
                    "visible_context": route_visible_context,
                    "base_visible_context": base_visible_context,
                    "current_turn_id": current_turn_id,
                },
            )
        else:
            previous_visible_context = visible_context if isinstance(visible_context, ContextSnapshot) else None
            responder_visible_context = self.context_compiler.build_snapshot(
                state=state,
                turn_input=turn_input,
                options=SnapshotCompileOptions(
                    history_window=resolved_history_window,
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
            if previous_visible_context is not None:
                responder_visible_context = replace(
                    responder_visible_context,
                    router_artifact_brief=dict(
                        getattr(previous_visible_context, "router_artifact_brief", {}) or {}
                    ),
                    router_plan=dict(
                        getattr(previous_visible_context, "router_plan", {}) or {}
                    ),
                )
            context = LLMContext(
                task=task,
                session_id=state.session_id,
                current_input=responder_visible_context.turn_input,
                history=list(responder_visible_context.history_messages),
                memory=dict(responder_visible_context.memory_projection or {}),
                multimodal={
                    "artifacts_count": len(responder_visible_context.artifacts),
                    "reference_artifacts_count": len(responder_visible_context.reference_artifacts),
                    "reference_artifacts_inherited": bool(responder_visible_context.reference_artifacts_inherited),
                    "router_artifact_brief": dict(responder_visible_context.router_artifact_brief or {}),
                },
                strategy=(plan.strategy.to_metadata() if plan is not None else None),
                routing=(decision.model_dump() if decision is not None else None),
                metadata={
                    "visible_context": responder_visible_context,
                    "current_turn_id": current_turn_id,
                },
            )
        if metadata:
            context.metadata.update(dict(metadata))
        context.metadata["state"] = state
        context.metadata["plan"] = plan
        context.metadata["decision"] = decision
        return context

    def route(self, context: LLMContext) -> InferenceResult:
        return self._execute(context)

    def generate(self, context: LLMContext) -> InferenceResult:
        return self._execute(context)

    def stream_generate(
        self,
        context: LLMContext,
        *,
        stop_event: threading.Event | None = None,
    ):
        provider = self._provider_for_context(context)
        stream_request = self._build_request(context, stream=True)
        yield from provider.stream(stream_request, stop_event=stop_event)

    def _build_request(self, context: LLMContext, *, stream: bool = False):
        request = self.request_builder.build(context)
        if not stream:
            return request
        return type(request)(**{**request.__dict__, "stream": True})

    def _execute(self, context: LLMContext) -> InferenceResult:
        provider = self._provider_for_context(context)
        request = self._build_request(context)
        return provider.chat(request)

    def _provider_for_context(self, context: LLMContext) -> OpenAIChatProvider:
        api_base = str((context.metadata or {}).get("api_base", "") or "").strip()
        api_key = str((context.metadata or {}).get("api_key", "") or "").strip()
        if api_base and api_key:
            return OpenAIChatProvider(api_base=api_base, api_key=api_key)
        return self.provider


def build_llm_service(prompt_center: PromptCenter) -> LLMService:
    return LLMService(prompt_center=prompt_center)
