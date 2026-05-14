import threading

from ava.capabilities.llm.context.builder import build_llm_context
from ava.capabilities.llm.providers.openai_chat import OpenAIChatProvider
from ava.capabilities.llm.requests.builder import InferenceRequestBuilder
from ava.capabilities.llm.types import InferenceResult, InferenceTask, LLMContext
from ava.capabilities.prompt.prompt_loader import PromptCenter


class LLMService:
    def __init__(
        self,
        *,
        prompt_center: PromptCenter,
        provider: OpenAIChatProvider | None = None,
        request_builder: InferenceRequestBuilder | None = None,
    ) -> None:
        self.prompt_center = prompt_center
        self.provider = provider or OpenAIChatProvider.from_settings()
        self.request_builder = request_builder or InferenceRequestBuilder(prompt_center)

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
        context = build_llm_context(
            task=task,
            state=state,
            turn_input=turn_input,
            decision=decision,
            plan=plan,
            history_window=history_window,
            max_context_messages=max_context_messages,
            current_turn_id=current_turn_id,
            visible_context=visible_context,
        )
        if metadata:
            context.metadata.update(dict(metadata))
        context.metadata["state"] = state
        context.metadata["plan"] = plan
        context.metadata["decision"] = decision
        return context

    def route(self, context: LLMContext) -> InferenceResult:
        request = self.request_builder.build(context)
        provider = self._provider_for_context(context)
        return provider.chat(request)

    def generate(self, context: LLMContext) -> InferenceResult:
        request = self.request_builder.build(context)
        provider = self._provider_for_context(context)
        return provider.chat(request)

    def stream_generate(
        self,
        context: LLMContext,
        *,
        stop_event: threading.Event | None = None,
    ):
        request = self.request_builder.build(context)
        provider = self._provider_for_context(context)
        stream_request = type(request)(
            **{
                **request.__dict__,
                "stream": True,
            }
        )
        yield from provider.stream(stream_request, stop_event=stop_event)

    def _provider_for_context(self, context: LLMContext) -> OpenAIChatProvider:
        api_base = str((context.metadata or {}).get("api_base", "") or "").strip()
        api_key = str((context.metadata or {}).get("api_key", "") or "").strip()
        if api_base and api_key:
            return OpenAIChatProvider(api_base=api_base, api_key=api_key)
        return self.provider


def build_llm_service(prompt_center: PromptCenter) -> LLMService:
    return LLMService(prompt_center=prompt_center)
