"""推理运行时主实现。"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

from ava.core.tracing import trace_event
from ava.domain.conversation.state import ConversationState
from ava.domain.conversation.state_patch import apply_state_patches
from ava.domain.multimodal.continuity import artifact_blocks, message_text
from ava.intent.orchestrator import OrchestrationContext, SkillOrchestrator
from ava.intent.planner import build_execution_plan
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
from ava.multi_turn_context_builder.runtime import build_runtime_payload, render_runtime_section
from configs import settings

from .types import TurnPlan

_SIMPLE_SCENES = {"general_qa", "casual_chat", "clarify"}


@dataclass
class ReplyExecutionResult:
    """回复执行结果。"""

    assistant_message: dict[str, Any]
    backend: str
    debug: dict[str, Any] = field(default_factory=dict)


def _assistant_message(text: str) -> dict[str, Any]:
    cleaned = str(text or "").strip()
    return {
        "role": "assistant",
        "content": [{"type": "output_text", "text": cleaned}] if cleaned else [],
    }


class ReplyService:
    """把已经准备好的 `TurnPlan` 真正送入模型执行器。"""

    def __init__(
            self,
            *,
            llm_service: LLMService | None = None,
            agent_backend: AgentBackend | None = None,
            orchestrator: SkillOrchestrator | None = None,
    ) -> None:
        self.llm_service = llm_service or LLMService()
        self.agent_backend = agent_backend or AgentBackend()
        self.orchestrator = orchestrator or SkillOrchestrator()

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

    def _select_model_tier(
            self,
            *,
            plan: TurnPlan,
            model: str,
            user_message: dict[str, Any] | None,
            session_id: str,
            current_turn_id: int | None,
    ) -> tuple[str, dict[str, Any]]:
        """按任务复杂度与路由置信度动态选模：小模型 → 大模型 → 兜底。"""
        base_model = str(model or plan.model or settings.openai_config.model or "").strip()
        selection: dict[str, Any] = {
            "tier": "large",
            "model": base_model,
            "reason": "default",
            "confidence": float(plan.decision.confidence or 0.0),
        }
        if not bool(getattr(settings.runtime, "model_selection_enabled", False)):
            return base_model, selection

        turn_scene = str(plan.decision.turn_scene or "").strip()
        text = message_text(user_message)
        has_artifacts = bool(artifact_blocks(user_message))
        small_model = str(getattr(settings.runtime, "small_model", "") or "").strip()
        min_confidence = float(getattr(settings.runtime, "model_selection_min_confidence", 0.75) or 0.75)
        is_simple = (
            turn_scene in _SIMPLE_SCENES
            and not has_artifacts
            and len(text) <= 80
            and float(plan.decision.confidence or 0.0) >= min_confidence
        )
        if is_simple and small_model:
            selection.update(tier="small", model=small_model, reason="low_complexity_high_confidence")
        elif has_artifacts:
            selection.update(tier="large", reason="multimodal_requires_large")
        elif turn_scene == "education":
            selection.update(tier="large", reason="education_requires_large")
        else:
            selection.update(tier="large", reason="complex_or_low_confidence")
        trace_event(
            "model.selected",
            actor="inference_runtime",
            session_id=session_id,
            turn_id=current_turn_id,
            **selection,
        )
        return selection["model"], selection

    def _continuity_metadata(
            self,
            *,
            state: ConversationState,
            user_message: dict[str, Any] | None,
            metadata: dict[str, Any],
    ) -> dict[str, Any]:
        """Responses API 模型侧连续对话：复用 previous_response_id，减少重复喂历史。"""
        merged = dict(metadata or {})
        if not bool(getattr(settings.runtime, "responder_continuity_enabled", False)):
            return merged
        if artifact_blocks(user_message):
            # 新附件需要完整多模态上下文，不走模型侧续接
            state.clear_responder_conversation_state()
            return merged
        previous = state.responder_conversation_state()
        if previous.get("previous_response_id"):
            merged["previous_response_id"] = previous["previous_response_id"]
        if previous.get("conversation_id"):
            merged["conversation_id"] = previous["conversation_id"]
        return merged

    @staticmethod
    def _write_back_continuity(state: ConversationState, response_metadata: dict[str, Any]) -> None:
        if not bool(getattr(settings.runtime, "responder_continuity_enabled", False)):
            return
        response_id = str((response_metadata or {}).get("response_id") or "").strip()
        conversation_id = str((response_metadata or {}).get("conversation_id") or "").strip()
        if response_id or conversation_id:
            state.update_responder_conversation_state(
                conversation_id=conversation_id or None,
                previous_response_id=response_id or None,
            )

    def _build_model_request_context(
            self,
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
            model=override_model or plan.model,
            instructions=plan.instructions,
            input=list(plan.input),
            metadata=merged_metadata,
        )

    def _maybe_orchestrate(
            self,
            *,
            state: ConversationState,
            plan: TurnPlan,
            user_message: dict[str, Any] | None,
            context: ConversationContext | None,
            current_turn_id: int | None,
            trace_id: str,
            on_token: Callable[[str], None] | None,
            stop_event=None,
    ) -> ReplyExecutionResult | None:
        """多意图 / 多技能子 Agent 编排路径（串行 / 并行 / 条件分支）。"""
        if not bool(getattr(settings.runtime, "multi_intent_enabled", False)):
            return None
        if user_message is None or context is None:
            return None
        execution_plan = build_execution_plan(
            decision=plan.decision,
            router_plan=plan.router_plan,
            mode=str(getattr(settings.runtime, "agents_sdk_orchestration_mode", "serial") or "serial"),
        )
        if not execution_plan.tasks:
            return None
        runtime_section = ""
        try:
            runtime_section = render_runtime_section(
                build_runtime_payload(
                    state=state,
                    context=context,
                    profile="responder",
                    decision=plan.decision,
                    strategy=plan.strategy,
                )
            )
        except Exception:
            runtime_section = ""
        orchestration_ctx = OrchestrationContext(
            session_id=state.session_id,
            turn_id=current_turn_id,
            trace_id=trace_id,
            state=state,
            conversation_context=context,
            decision=plan.decision,
            router_plan=dict(plan.router_plan or {}),
            user_message=dict(user_message),
            runtime_section=runtime_section,
        )
        outcome = self.orchestrator.run(execution_plan, orchestration_ctx, stop_event=stop_event)
        patch_result = apply_state_patches(
            state,
            outcome.patches,
            actor="orchestrator",
            trace_id=trace_id,
        )
        if on_token is not None and outcome.merged_text:
            text = outcome.merged_text
            for index in range(0, len(text), 24):
                if stop_event is not None and stop_event.is_set():
                    break
                on_token(text[index: index + 24])
        return ReplyExecutionResult(
            assistant_message=_assistant_message(outcome.merged_text),
            backend="skill_orchestrator",
            debug={
                "orchestration": outcome.model_dump(mode="json"),
                "applied_state_patches": list(patch_result["applied"]),
                "rejected_state_patches": list(patch_result["rejected"]),
                "agent_debug_events": list(outcome.events),
            },
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
            trace_id: str = "",
    ) -> ReplyExecutionResult:
        orchestrated = self._maybe_orchestrate(
            state=state,
            plan=plan,
            user_message=user_message,
            context=context,
            current_turn_id=current_turn_id,
            trace_id=trace_id,
            on_token=None,
        )
        if orchestrated is not None:
            return orchestrated

        selected_model, selection = self._select_model_tier(
            plan=plan,
            model=model,
            user_message=user_message,
            session_id=session_id,
            current_turn_id=current_turn_id,
        )
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
                model=selected_model or str(settings.openai_config.model or "").strip(),
                timeout=int((metadata or {}).get("timeout") or settings.openai_config.timeout),
                current_turn_id=current_turn_id,
            )
            return ReplyExecutionResult(
                assistant_message=result.assistant_message,
                backend=result.backend,
                debug={
                    "agent_debug_events": list(result.debug_events),
                    "applied_state_patches": list(result.applied_patches),
                    "model_selection": selection,
                },
            )

        request_metadata = self._continuity_metadata(
            state=state,
            user_message=user_message,
            metadata=dict(metadata or {}),
        )
        request = self._build_model_request_context(
            session_id=session_id,
            plan=plan,
            model=selected_model,
            metadata=request_metadata,
        )
        try:
            result = self.llm_service.generate(request)
        except Exception as exc:
            fallback_model = str(getattr(settings.runtime, "fallback_model", "") or "").strip()
            if not fallback_model or fallback_model == selected_model:
                raise
            trace_event(
                "model.fallback",
                actor="inference_runtime",
                session_id=session_id,
                turn_id=current_turn_id,
                trace_id=trace_id,
                from_model=selected_model,
                to_model=fallback_model,
                error=str(exc)[:200],
            )
            request = self._build_model_request_context(
                session_id=session_id,
                plan=plan,
                model=fallback_model,
                metadata=dict(metadata or {}),
            )
            result = self.llm_service.generate(request)
            selection = {**selection, "tier": "fallback", "model": fallback_model, "reason": "primary_failed"}
        self._write_back_continuity(state, dict(result.metadata or {}))
        return ReplyExecutionResult(
            assistant_message=_assistant_message(result.text),
            backend="llm_responses",
            debug={
                "response_metadata": dict(result.metadata or {}),
                "model_selection": selection,
            },
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
            trace_id: str = "",
    ) -> ReplyExecutionResult:
        orchestrated = self._maybe_orchestrate(
            state=state,
            plan=plan,
            user_message=user_message,
            context=context,
            current_turn_id=current_turn_id,
            trace_id=trace_id,
            on_token=on_token,
            stop_event=stop_event,
        )
        if orchestrated is not None:
            return orchestrated

        selected_model, selection = self._select_model_tier(
            plan=plan,
            model=model,
            user_message=user_message,
            session_id=session_id,
            current_turn_id=current_turn_id,
        )
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
                model=selected_model or str(settings.openai_config.model or "").strip(),
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
                    "model_selection": selection,
                },
            )

        request_metadata = self._continuity_metadata(
            state=state,
            user_message=user_message,
            metadata=dict(metadata or {}),
        )
        request = self._build_model_request_context(
            session_id=session_id,
            plan=plan,
            model=selected_model,
            metadata=request_metadata,
        )
        parts: list[str] = []
        final_metadata: dict[str, Any] = {}
        started_at = time.monotonic()
        first_token_ms: float | None = None
        try:
            for event in self.llm_service.stream_generate(request, stop_event=stop_event):
                if isinstance(event, OutputTextDelta):
                    if first_token_ms is None:
                        first_token_ms = round((time.monotonic() - started_at) * 1000, 2)
                    parts.append(event.text)
                    on_token(event.text)
                elif isinstance(event, InferenceCompleted):
                    final_metadata = dict(event.metadata or {})
                elif isinstance(event, InferenceError):
                    raise RuntimeError(event.error)
        except Exception as exc:
            fallback_model = str(getattr(settings.runtime, "fallback_model", "") or "").strip()
            if not fallback_model or fallback_model == selected_model or parts:
                raise
            trace_event(
                "model.fallback",
                actor="inference_runtime",
                session_id=session_id,
                turn_id=current_turn_id,
                trace_id=trace_id,
                from_model=selected_model,
                to_model=fallback_model,
                error=str(exc)[:200],
            )
            request = self._build_model_request_context(
                session_id=session_id,
                plan=plan,
                model=fallback_model,
                metadata=dict(metadata or {}),
            )
            for event in self.llm_service.stream_generate(request, stop_event=stop_event):
                if isinstance(event, OutputTextDelta):
                    parts.append(event.text)
                    on_token(event.text)
                elif isinstance(event, InferenceCompleted):
                    final_metadata = dict(event.metadata or {})
                elif isinstance(event, InferenceError):
                    raise RuntimeError(event.error)
            selection = {**selection, "tier": "fallback", "model": fallback_model, "reason": "primary_failed"}
        self._write_back_continuity(state, final_metadata)
        if first_token_ms is not None:
            trace_event(
                "llm.first_token",
                actor="inference_runtime",
                session_id=session_id,
                turn_id=current_turn_id,
                trace_id=trace_id,
                latency_ms=first_token_ms,
                model=selection.get("model", ""),
            )
        return ReplyExecutionResult(
            assistant_message=_assistant_message("".join(parts)),
            backend="llm_responses_stream",
            debug={
                "response_metadata": final_metadata,
                "model_selection": selection,
                "first_token_ms": first_token_ms,
            },
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
            trace_id: str = "",
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
            trace_id=trace_id,
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
            trace_id: str = "",
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
            trace_id=trace_id,
        )