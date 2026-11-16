"""路由选择主实现。"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from ava.capabilities.prompt import build_responder_prompt_package
from ava.capabilities.prompt.prompt_loader import PromptCenter
from ava.core.tracing import trace_event
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
from ava.multi_turn_context_builder.compiler import context_snapshot_hash
from ava.router_selector.edge_cloud import RouteCache, build_edge_request_context, route_fingerprint
from ava.router_selector.strategy_builder import build_strategy_from_model_plan
from configs import settings

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
        self._route_cache = RouteCache()

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
            state=state,
        )
        return RouterRequestArtifacts(
            context=current_context,
            instructions=payload.instructions,
            input=list(payload.input),
            active_skills=list(payload.active_skills),
            metadata={
                "profile": current_context.session.profile,
                "sections": dict(payload.sections or {}),
                "layers": dict(payload.layers or {}),
                "context_snapshot": context_snapshot_hash(payload.instructions, list(payload.input)),
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
            trace_id: str = "",
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
        fingerprint = route_fingerprint(
            context_snapshot=str(request.metadata.get("context_snapshot", "") or ""),
            session_scene=route_context.session.session_scene,
            model=request_context.model,
        )
        cache_enabled = bool(settings.runtime.route_cache_enabled)
        if cache_enabled:
            cached = self._route_cache.get(
                fingerprint, ttl_seconds=float(settings.runtime.route_cache_ttl_seconds)
            )
            if cached is not None:
                trace_event(
                    "route.cache_hit",
                    actor="router",
                    session_id=state.session_id,
                    turn_id=current_turn_id,
                    trace_id=trace_id,
                    fingerprint=fingerprint,
                )
                cached_decision = self.policy.apply(
                    RouteDecision.model_validate(cached["decision"]),
                    current_session_scene=route_context.session.session_scene,
                )
                return RouterResult(
                    decision=cached_decision,
                    context=route_context,
                    router_plan=dict(cached.get("router_plan") or {}),
                    request_payload={"instructions": request.instructions, "input": list(request.input)},
                    raw_output=str(cached.get("raw_output") or ""),
                    selection_summary={
                        "session_id": state.session_id,
                        "turn_id": current_turn_id,
                        "session_scene": cached_decision.session_scene,
                        "turn_scene": cached_decision.turn_scene,
                        "intent": cached_decision.intent,
                        "confidence": cached_decision.confidence,
                        "router_plan": dict(cached.get("router_plan") or {}),
                        "latency_ms": 0.0,
                        "model": str(cached.get("model") or request_context.model),
                        "context_snapshot": request.metadata.get("context_snapshot", ""),
                        "cache_hit": True,
                    },
                )

        raw_output, parsed, latency_ms, model_used, provider = self._execute_route(
            request_context,
            session_id=state.session_id,
            turn_id=current_turn_id,
            trace_id=trace_id,
        )
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
            "latency_ms": latency_ms,
            "model": model_used,
            "provider": provider,
            "context_snapshot": request.metadata.get("context_snapshot", ""),
            "cache_hit": False,
        }
        trace_event(
            "route.decision",
            actor="router",
            session_id=state.session_id,
            turn_id=current_turn_id,
            trace_id=trace_id,
            latency_ms=latency_ms,
            decision=final_decision.model_dump(),
            router_plan=router_plan,
            model=model_used,
            provider=provider,
            context_snapshot=request.metadata.get("context_snapshot", ""),
            raw_output=raw_output[:600],
        )
        if cache_enabled:
            self._route_cache.put(
                fingerprint,
                {
                    "decision": final_decision.model_dump(),
                    "router_plan": router_plan,
                    "raw_output": raw_output,
                    "model": model_used,
                },
            )
        return RouterResult(
            decision=final_decision,
            context=route_context,
            router_plan=router_plan,
            request_payload={"instructions": request.instructions, "input": list(request.input)},
            raw_output=raw_output,
            selection_summary=selection_summary,
        )

    def _execute_route(
            self,
            request_context: ModelRequestContext,
            *,
            session_id: str,
            turn_id: int | None,
            trace_id: str,
    ) -> tuple[str, dict[str, Any], float, str, str]:
        """端侧小模型优先，失败/超时/低置信降级云侧。"""
        intent = settings.intent_config
        if intent.enabled and str(intent.provider or "").strip() == "local":
            local = intent.local
            edge_context = build_edge_request_context(
                request_context,
                api_base=local.api_base,
                api_key=local.api_key,
                model=local.model,
                timeout_ms=int(local.timeout_ms),
                no_think=bool(local.no_think),
            )
            fallback_reason = ""
            started_at = time.monotonic()
            try:
                edge_result = self.llm_service.route(edge_context)
                edge_latency = round((time.monotonic() - started_at) * 1000, 2)
                edge_parsed = self._extract_json_object(str(edge_result.text or ""))
                edge_decision = RouteDecision.model_validate(
                    {key: value for key, value in edge_parsed.items() if key != "plan"}
                )
                trace_event(
                    "intent.edge_result",
                    actor="router",
                    session_id=session_id,
                    turn_id=turn_id,
                    trace_id=trace_id,
                    latency_ms=edge_latency,
                    model=edge_context.model,
                    confidence=edge_decision.confidence,
                )
                if edge_decision.confidence >= float(intent.min_confidence):
                    return str(edge_result.text or ""), edge_parsed, edge_latency, edge_context.model, "edge_local"
                fallback_reason = "low_confidence"
            except Exception as exc:
                fallback_reason = f"edge_error:{str(exc)[:160]}"
            if not intent.cloud_fallback_enabled:
                raise RuntimeError(f"edge route failed and cloud fallback disabled: {fallback_reason}")
            trace_event(
                "intent.fallback",
                actor="router",
                session_id=session_id,
                turn_id=turn_id,
                trace_id=trace_id,
                reason=fallback_reason,
                edge_model=edge_context.model,
                cloud_model=request_context.model,
            )
        started_at = time.monotonic()
        result = self.llm_service.route(request_context)
        latency_ms = round((time.monotonic() - started_at) * 1000, 2)
        raw_output = str(result.text or "")
        parsed = self._extract_json_object(raw_output)
        return raw_output, parsed, latency_ms, request_context.model, "cloud"

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
            responder_max_context_messages: int | None = None,
            responder_context: ConversationContext | None = None,
            trace_id: str = "",
    ) -> TurnPlan:
        responder_context = responder_context or self.context_compiler.build_conversation_context(
            state=state,
            user_message=user_message,
            options=ConversationBuildOptions(
                history_window=history_window,
                current_turn_id=current_turn_id,
                max_context_messages=responder_max_context_messages or max_context_messages,
                profile="responder",
            ),
        )
        selected_strategy = strategy
        if selected_strategy is None:
            selected_strategy = build_strategy_from_model_plan(
                prompt_center,
                decision,
                responder_context,
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
            context=responder_context,
            strategy=selected_strategy,
            decision=decision,
            state=state,
        )
        snapshot = context_snapshot_hash(payload.instructions, list(payload.input))
        trace_event(
            "context.compiled",
            actor="context_compiler",
            session_id=state.session_id,
            turn_id=current_turn_id,
            trace_id=trace_id,
            profile="responder",
            context_snapshot=snapshot,
            active_skills=list(selected_prompt_package.skill_names()),
            layers={
                "system_chars": len(payload.layers.get("system", "")),
                "developer_chars": len(payload.layers.get("developer", "")),
                "history_messages": len(payload.layers.get("history", [])),
            },
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
                conversation_context=responder_context,
            ),
            debug=TurnPlanDebug(
                router_plan=dict(router_plan or {}),
                active_skills=active_skill_names,
                prompt_package=selected_prompt_package.to_metadata(),
                context_layers=dict(payload.layers or {}),
                context_snapshot=snapshot,
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
            responder_max_context_messages: int | None = None,
            trace_id: str = "",
    ) -> PreparedTurn:
        # 并行预取：Responder 上下文不依赖路由结果，与路由调用重叠执行
        prefetch_executor: ThreadPoolExecutor | None = None
        prefetch_future = None
        if bool(settings.runtime.parallel_prefetch_enabled):
            prefetch_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ctx-prefetch")
            prefetch_future = prefetch_executor.submit(
                self.context_compiler.build_conversation_context,
                state=state,
                user_message=user_message,
                options=ConversationBuildOptions(
                    history_window=history_window,
                    current_turn_id=current_turn_id,
                    max_context_messages=responder_max_context_messages or max_context_messages,
                    profile="responder",
                ),
            )
        try:
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
                trace_id=trace_id,
            )
            prefetched_context = prefetch_future.result() if prefetch_future is not None else None
        finally:
            if prefetch_executor is not None:
                prefetch_executor.shutdown(wait=False)
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
            responder_max_context_messages=responder_max_context_messages,
            responder_context=prefetched_context,
            trace_id=trace_id,
        )
        return PreparedTurn(
            route_result=route_result,
            turn_plan=turn_plan,
        )
