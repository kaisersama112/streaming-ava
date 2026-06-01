"""推理运行时主实现。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from ava.domain.conversation.state import ConversationState
from ava.llm_model_executor.agent_backend import AgentBackend
from ava.llm_model_executor.service import LLMService
from ava.llm_model_executor.types import (
    InferenceCompleted,
    InferenceError,
    InferenceTask,
    ModelRequestContext,
    OutputTextDelta,
)
from ava.multi_turn_context_builder import ContextCompiler, ConversationContext
from configs import settings

from .types import TurnPlan


@dataclass
class ReplyExecutionResult:
    """回复执行结果。"""

    assistant_message: dict[str, Any]
    backend: str
    debug: dict[str, Any] = field(default_factory=dict)


class ReplyService:
    """把已经准备好的 `TurnPlan` 真正送入模型执行器。"""

    def __init__(
            self,
            *,
            llm_service: LLMService | None = None,
            agent_backend: AgentBackend | None = None,
    ) -> None:
        self.llm_service = llm_service or LLMService()
        self.agent_backend = agent_backend or AgentBackend()

    def _should_use_agents_backend(self, *, plan: TurnPlan, realtime: bool) -> bool:
        if not bool(getattr(settings.runtime, "agents_sdk_enabled", False)):
            return False
        if realtime and not bool(getattr(settings.runtime, "agents_sdk_realtime_enabled", False)):
            return False
        allowed_branches = [
            str(item or "").strip()
            for item in list(getattr(settings.runtime, "agents_sdk_branches", []) or [])
            if str(item or "").strip()
        ]
        current_turn_scene = str(plan.decision.turn_scene or "").strip()
        if allowed_branches and current_turn_scene not in set(allowed_branches):
            return False
        allowed_modules = [
            str(item or "").strip()
            for item in list(getattr(settings.runtime, "agents_sdk_education_modules", []) or [])
            if str(item or "").strip()
        ]
        if current_turn_scene == "education" and allowed_modules:
            task_name = str(plan.prompt_profile.get("task") or "").strip()
            return task_name in set(allowed_modules)
        return True

    @staticmethod
    def _build_model_request_context(
            *,
            session_id: str,
            plan: TurnPlan,
            model: str,
            metadata: dict[str, Any] | None = None,
    ) -> ModelRequestContext:
        """把 `TurnPlan` 显式转换为模型执行层请求对象。"""
        override_model = str(model or plan.model or "").strip()
        merged_metadata = dict(metadata or {})
        if override_model:
            merged_metadata["model_override"] = override_model
        return ModelRequestContext(
            task=InferenceTask.GENERATE,
            session_id=session_id,
            model=plan.model,
            instructions=plan.instructions,
            input=list(plan.input),
            metadata=merged_metadata,
        )

    def generate(
            self,
            *,
            state: ConversationState,
            session_id: str,
            plan: TurnPlan,
            model: str,
            user_message: dict[str, Any] | None = None,
            context: ConversationContext | None = None,
            current_turn_id: int | None = None,
            metadata: dict[str, Any] | None = None,
    ) -> ReplyExecutionResult:
        if (
                self._should_use_agents_backend(plan=plan, realtime=False)
                and user_message is not None
                and context is not None
        ):
            result = self.agent_backend.run_sync(
                state=state,
                user_message=user_message,
                decision=plan.decision,
                plan=plan,
                context=context,
                api_base=str((metadata or {}).get("api_base") or settings.openai_config.api_base or "").strip(),
                api_key=str((metadata or {}).get("api_key") or settings.openai_config.api_key or "").strip(),
                model=str(model or plan.model or "").strip() or str(settings.openai_config.model or "").strip(),
                timeout=int((metadata or {}).get("timeout") or settings.openai_config.timeout),
                current_turn_id=current_turn_id,
            )
            return ReplyExecutionResult(
                assistant_message=result.assistant_message,
                backend=result.backend,
                debug={
                    "agent_debug_events": list(result.debug_events),
                    "applied_state_patches": list(result.applied_patches),
                },
            )

        request = self._build_model_request_context(
            session_id=session_id,
            plan=plan,
            model=model,
            metadata=dict(metadata or {}),
        )
        result = self.llm_service.generate(request)
        return ReplyExecutionResult(
            assistant_message={
                "role": "assistant",
                "content": (
                    [{"type": "output_text", "text": str(result.text or "").strip()}]
                    if str(result.text or "").strip()
                    else []
                ),
            },
            backend="llm_responses",
            debug={"response_metadata": dict(result.metadata or {})},
        )

    def stream(
            self,
            *,
            state: ConversationState,
            session_id: str,
            plan: TurnPlan,
            model: str,
            on_token: Callable[[str], None],
            user_message: dict[str, Any] | None = None,
            context: ConversationContext | None = None,
            current_turn_id: int | None = None,
            metadata: dict[str, Any] | None = None,
            stop_event=None,
    ) -> ReplyExecutionResult:
        if (
                self._should_use_agents_backend(plan=plan, realtime=True)
                and user_message is not None
                and context is not None
        ):
            result = self.agent_backend.run_stream(
                state=state,
                user_message=user_message,
                decision=plan.decision,
                plan=plan,
                context=context,
                api_base=str((metadata or {}).get("api_base") or settings.openai_config.api_base or "").strip(),
                api_key=str((metadata or {}).get("api_key") or settings.openai_config.api_key or "").strip(),
                model=str(model or plan.model or "").strip() or str(settings.openai_config.model or "").strip(),
                timeout=int((metadata or {}).get("timeout") or settings.openai_config.timeout),
                on_token=on_token,
                current_turn_id=current_turn_id,
                stop_event=stop_event,
            )
            return ReplyExecutionResult(
                assistant_message=result.assistant_message,
                backend=result.backend,
                debug={
                    "agent_debug_events": list(result.debug_events),
                    "applied_state_patches": list(result.applied_patches),
                },
            )

        request = self._build_model_request_context(
            session_id=session_id,
            plan=plan,
            model=model,
            metadata=dict(metadata or {}),
        )
        parts: list[str] = []
        final_metadata: dict[str, Any] = {}
        for event in self.llm_service.stream_generate(request, stop_event=stop_event):
            if isinstance(event, OutputTextDelta):
                parts.append(event.text)
                on_token(event.text)
            elif isinstance(event, InferenceCompleted):
                final_metadata = dict(event.metadata or {})
            elif isinstance(event, InferenceError):
                raise RuntimeError(event.error)
        return ReplyExecutionResult(
            assistant_message={
                "role": "assistant",
                "content": (
                    [{"type": "output_text", "text": "".join(parts).strip()}]
                    if "".join(parts).strip()
                    else []
                ),
            },
            backend="llm_responses_stream",
            debug={"response_metadata": final_metadata},
        )


class InferenceRuntime:
    """独立推理运行时。

    当前版本只消费外部已经准备好的 `TurnPlan`，
    不再在内部负责路由、策略生成或计划构建。
    """

    def __init__(
            self,
            *,
            context_compiler: ContextCompiler | None = None,
            llm_service: LLMService | None = None,
            reply_service: ReplyService | None = None,
    ) -> None:
        self.context_compiler = context_compiler or ContextCompiler()
        self.llm_service = llm_service or LLMService()
        self.reply_service = reply_service or ReplyService(
            llm_service=self.llm_service,
        )

    def generate_reply(
            self,
            *,
            state: ConversationState,
            user_message: dict[str, Any],
            context: ConversationContext,
            plan: TurnPlan,
            current_turn_id: int | None = None,
            model: str = "",
            metadata: dict[str, Any] | None = None,
    ) -> ReplyExecutionResult:
        return self.reply_service.generate(
            state=state,
            session_id=state.session_id,
            plan=plan,
            model=model,
            user_message=user_message,
            context=context,
            current_turn_id=current_turn_id,
            metadata=dict(metadata or {}),
        )

    def stream_reply(
            self,
            *,
            state: ConversationState,
            user_message: dict[str, Any],
            context: ConversationContext,
            plan: TurnPlan,
            on_token: Callable[[str], None],
            current_turn_id: int | None = None,
            model: str = "",
            metadata: dict[str, Any] | None = None,
            stop_event=None,
    ) -> ReplyExecutionResult:
        return self.reply_service.stream(
            state=state,
            session_id=state.session_id,
            plan=plan,
            model=model,
            on_token=on_token,
            user_message=user_message,
            context=context,
            current_turn_id=current_turn_id,
            metadata=dict(metadata or {}),
            stop_event=stop_event,
        )
