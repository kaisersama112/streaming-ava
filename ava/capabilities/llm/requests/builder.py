from ava.capabilities.llm.requests.policy import (
    resolve_model,
    resolve_temperature,
    resolve_timeout,
)
from ava.capabilities.llm.types import InferenceRequest, InferenceTask, LLMContext
from ava.capabilities.prompt.prompt_loader import PromptCenter
from ava.context_engine.compiler import ContextCompiler
from ava.context_engine.types import ContextSnapshot, SnapshotCompileOptions
from ava.domain.conversation.strategy import BranchStrategy


class InferenceRequestBuilder:
    def __init__(
        self,
        prompt_center: PromptCenter,
        compiler: ContextCompiler | None = None,
    ) -> None:
        self.prompt_center = prompt_center
        self.compiler = compiler or ContextCompiler()

    def _visible_context(self, context: LLMContext) -> ContextSnapshot:
        visible_context = context.metadata.get("visible_context")
        if not isinstance(visible_context, ContextSnapshot):
            raise ValueError("LLMContext metadata is missing ContextSnapshot.")
        return visible_context

    def build(self, context: LLMContext) -> InferenceRequest:
        visible_context = self._visible_context(context)
        state = context.metadata.get("state")
        if state is None:
            raise ValueError("LLMContext metadata is missing state.")

        current_turn_id = context.metadata.get("current_turn_id")
        max_context_messages = max(len(visible_context.history_messages), 1)
        options = SnapshotCompileOptions(
            history_window=max(1, max_context_messages // 2 or 1),
            current_turn_id=current_turn_id,
            max_context_messages=max_context_messages,
            profile=visible_context.context_profile,
        )

        if context.task == InferenceTask.ROUTE:
            envelope = self.compiler.compile_router_envelope(
                prompt_center=self.prompt_center,
                state=state,
                turn_input=context.current_input,
                options=options,
                snapshot=visible_context,
                text_only=bool((context.routing or {}).get("text_only_router", False)),
            )
            return InferenceRequest(
                task=context.task,
                model=resolve_model(context),
                instructions=envelope.instructions,
                input_items=[
                    dict(message)
                    for message in envelope.messages[1:]
                ],
                stream=False,
                temperature=resolve_temperature(context),
                timeout=resolve_timeout(context),
                modalities=["text"],
                extra_body={
                    "metadata": {"inference_context": envelope.runtime_context},
                },
                metadata={
                    "compiled_envelope": envelope,
                    "inference_context": envelope.runtime_context,
                    "active_skills": envelope.active_skills,
                },
            )

        plan = context.metadata.get("plan")
        strategy = getattr(plan, "strategy", None) if plan is not None else None
        if not isinstance(strategy, BranchStrategy):
            raise ValueError("Generate context is missing plan.strategy for prompt resolution.")

        envelope = self.compiler.compile_responder_envelope(
            prompt_center=self.prompt_center,
            state=state,
            turn_input=context.current_input,
            strategy=strategy,
            decision=context.metadata.get("decision"),
            options=options,
            snapshot=visible_context,
            previous_snapshot=context.metadata.get("base_visible_context"),
        )
        responder_conversation_state = (
            state.responder_conversation_state()
            if hasattr(state, "responder_conversation_state")
            else {}
        )
        responder_conversation_id = str(
            responder_conversation_state.get("conversation_id", "") or ""
        ).strip()
        responder_previous_response_id = str(
            responder_conversation_state.get("previous_response_id", "") or ""
        ).strip()
        has_stateful_chain = bool(responder_conversation_id or responder_previous_response_id)
        input_items = (
            [dict(envelope.messages[-1])]
            if has_stateful_chain
            else [dict(message) for message in envelope.messages[1:]]
        )
        return InferenceRequest(
            task=context.task,
            model=resolve_model(context),
            instructions=envelope.instructions,
            input_items=input_items,
            conversation=(responder_conversation_id or None),
            previous_response_id=(
                responder_previous_response_id if responder_previous_response_id and not responder_conversation_id else None
            ),
            stream=False,
            temperature=resolve_temperature(context),
            timeout=resolve_timeout(context),
            modalities=["text"],
            extra_body={
                "metadata": {"inference_context": envelope.runtime_context},
            },
            metadata={
                "compiled_envelope": envelope,
                "inference_context": envelope.runtime_context,
                "active_skills": envelope.active_skills,
                "strategy": dict(context.strategy or {}),
                "use_conversation_state": True,
            },
        )
