"""技能子 Agent 编排器：串行 / 并行 / 条件分支。

设计约束：
- 子 Agent 只产出文本与 patch 建议，状态写入统一走白名单 apply_state_patches
- 条件分支使用注册谓词，绝不 eval 模型输出
- 支持 stop_event 取消（barge-in），已完成结果保留用于未完成 turn 上下文
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from ava.core.tracing import trace_event
from ava.domain.multimodal.continuity import artifact_blocks, message_text

from . import protocol
from .types import ExecutionPlan, IntentItem, OrchestrationOutcome, SubAgentResult


@dataclass
class OrchestrationContext:
    """编排期只读上下文 + 已完成结果。"""

    session_id: str = ""
    turn_id: int | None = None
    trace_id: str = ""
    state: Any = None
    conversation_context: Any = None
    decision: Any = None
    router_plan: dict[str, Any] = field(default_factory=dict)
    user_message: dict[str, Any] = field(default_factory=dict)
    runtime_section: str = ""
    results: dict[str, SubAgentResult] = field(default_factory=dict)

    @property
    def has_artifacts(self) -> bool:
        return bool(artifact_blocks(self.user_message))

    @property
    def user_text(self) -> str:
        return message_text(self.user_message)

    def result_of(self, task_id: str) -> SubAgentResult | None:
        return self.results.get(task_id)


Predicate = Callable[[OrchestrationContext, IntentItem], bool]


def _has_student_work(ctx: OrchestrationContext, task: IntentItem) -> bool:
    del task
    memory = getattr(ctx.state, "memory", None)
    if memory is None:
        return False
    artifacts = artifact_blocks(ctx.user_message)
    if not artifacts:
        return False
    from ava.domain.multimodal.continuity import blocks_to_artifacts

    analysis = memory.cached_or_metadata_block_analysis(blocks_to_artifacts(artifacts))
    return bool(analysis.get("contains_student_work"))


def _previous_ok(ctx: OrchestrationContext, task: IntentItem) -> bool:
    return any(ctx.result_of(dep) is not None and ctx.result_of(dep).status == "ok" for dep in task.depends_on)


def _previous_failed(ctx: OrchestrationContext, task: IntentItem) -> bool:
    return any(ctx.result_of(dep) is not None and ctx.result_of(dep).status == "error" for dep in task.depends_on)


def _high_confidence(ctx: OrchestrationContext, task: IntentItem) -> bool:
    threshold = float(task.params.get("min_confidence", 0.7) or 0.7)
    return float(task.confidence or 0.0) >= threshold


def _has_artifacts(ctx: OrchestrationContext, task: IntentItem) -> bool:
    del task
    return ctx.has_artifacts


def _text_contains(ctx: OrchestrationContext, task: IntentItem) -> bool:
    needle = str(task.params.get("needle", "") or "").strip()
    return bool(needle) and needle in ctx.user_text


PREDICATES: dict[str, Predicate] = {
    "has_student_work": _has_student_work,
    "has_artifacts": _has_artifacts,
    "previous_ok": _previous_ok,
    "previous_failed": _previous_failed,
    "high_confidence": _high_confidence,
    "text_contains": _text_contains,
}


class SkillRunner(Protocol):
    def __call__(
        self,
        task: IntentItem,
        ctx: OrchestrationContext,
        *,
        stop_event: threading.Event | None = None,
    ) -> SubAgentResult: ...


def merge_results(plan: ExecutionPlan, results: list[SubAgentResult]) -> str:
    """多意图合并为一条统一回复。"""
    ordered = [item for item in results if item.status == "ok" and item.text.strip()]
    if not ordered:
        return ""
    if plan.merge == "primary":
        return ordered[0].text.strip()
    if len(ordered) == 1:
        return ordered[0].text.strip()
    return "\n\n".join(item.text.strip() for item in ordered)


class SkillOrchestrator:
    """按 ExecutionPlan 调度技能子 Agent。"""

    def __init__(
        self,
        *,
        runner: SkillRunner | None = None,
        prompt_center: Any = None,
        max_parallel: int = 3,
    ) -> None:
        self._runner = runner
        self.prompt_center = prompt_center
        self.max_parallel = max(1, int(max_parallel or 3))

    @property
    def runner(self) -> SkillRunner:
        if self._runner is None:
            from .runner import AgentsSDKSkillRunner

            self._runner = AgentsSDKSkillRunner(prompt_center=self.prompt_center)
        return self._runner

    def _trace_kwargs(self, ctx: OrchestrationContext) -> dict[str, Any]:
        return {
            "session_id": ctx.session_id,
            "turn_id": ctx.turn_id,
            "trace_id": ctx.trace_id,
        }

    def _evaluate_condition(self, task: IntentItem, ctx: OrchestrationContext) -> tuple[bool, str]:
        name = str(task.condition or "").strip()
        if not name:
            return True, ""
        predicate = PREDICATES.get(name)
        if predicate is None:
            return False, f"unknown_predicate:{name}"
        try:
            return bool(predicate(ctx, task)), name
        except Exception as exc:
            return False, f"predicate_error:{exc}"

    def _dispatch(
        self,
        task: IntentItem,
        ctx: OrchestrationContext,
        *,
        stop_event: threading.Event | None,
        events: list[dict[str, Any]],
    ) -> SubAgentResult:
        correlation_id = f"{ctx.trace_id or ctx.session_id}:{task.task_id or task.skill}"
        assign = protocol.task_assign(
            task,
            correlation_id=correlation_id,
            session_id=ctx.session_id,
            turn_id=ctx.turn_id,
            trace_id=ctx.trace_id,
        )
        events.append(assign.to_payload())
        trace_event("agent.task.assigned", actor="manager", **self._trace_kwargs(ctx), task=task.model_dump(mode="json"))

        if stop_event is not None and stop_event.is_set():
            result = SubAgentResult(task_id=task.task_id, skill=task.skill, status="cancelled")
            events.append(protocol.control_cancel(correlation_id=correlation_id, **self._trace_kwargs(ctx)).to_payload())
            ctx.results[task.task_id] = result
            return result

        allowed, condition = self._evaluate_condition(task, ctx)
        if not allowed:
            result = SubAgentResult(task_id=task.task_id, skill=task.skill, status="skipped", error=condition)
            events.append(
                protocol.task_result(result, correlation_id=correlation_id, **self._trace_kwargs(ctx)).to_payload()
            )
            trace_event(
                "agent.task.skipped",
                actor="manager",
                **self._trace_kwargs(ctx),
                task_id=task.task_id,
                skill=task.skill,
                condition=condition,
            )
            ctx.results[task.task_id] = result
            return result

        started_at = time.monotonic()
        try:
            result = self.runner(task, ctx, stop_event=stop_event)
        except Exception as exc:
            result = SubAgentResult(task_id=task.task_id, skill=task.skill, status="error", error=str(exc))
        result.latency_ms = round((time.monotonic() - started_at) * 1000, 2)
        result.task_id = result.task_id or task.task_id
        result.skill = result.skill or task.skill
        ctx.results[task.task_id] = result

        if result.status == "error":
            events.append(
                protocol.task_error(
                    task.task_id, task.skill, result.error, correlation_id=correlation_id, **self._trace_kwargs(ctx)
                ).to_payload()
            )
            trace_event(
                "agent.task.error",
                actor=f"skill:{task.skill}",
                latency_ms=result.latency_ms,
                **self._trace_kwargs(ctx),
                task_id=task.task_id,
                error=result.error[:300],
            )
        else:
            events.append(
                protocol.task_result(result, correlation_id=correlation_id, **self._trace_kwargs(ctx)).to_payload()
            )
            trace_event(
                "agent.task.result",
                actor=f"skill:{task.skill}",
                latency_ms=result.latency_ms,
                **self._trace_kwargs(ctx),
                task_id=task.task_id,
                status=result.status,
                text_chars=len(result.text),
                patches=len(result.patches),
            )
        if result.patches:
            events.append(
                protocol.state_patch(
                    result.patches,
                    actor=f"skill:{task.skill}",
                    correlation_id=correlation_id,
                    **self._trace_kwargs(ctx),
                ).to_payload()
            )
        return result

    def run(
        self,
        plan: ExecutionPlan,
        ctx: OrchestrationContext,
        *,
        stop_event: threading.Event | None = None,
    ) -> OrchestrationOutcome:
        started_at = time.monotonic()
        events: list[dict[str, Any]] = []
        results: list[SubAgentResult] = []
        ordered = plan.ordered_tasks()
        mode = plan.mode

        if mode == "parallel":
            results = self._run_parallel(plan, ordered, ctx, stop_event=stop_event, events=events)
        else:
            for task in ordered:
                if stop_event is not None and stop_event.is_set():
                    results.append(
                        SubAgentResult(task_id=task.task_id, skill=task.skill, status="cancelled")
                    )
                    continue
                results.append(self._dispatch(task, ctx, stop_event=stop_event, events=events))

        patches = [patch for item in results for patch in item.patches]
        outcome = OrchestrationOutcome(
            mode=mode,
            results=results,
            merged_text=merge_results(plan, results),
            patches=patches,
            events=events,
            latency_ms=round((time.monotonic() - started_at) * 1000, 2),
        )
        trace_event(
            "orchestration.done",
            actor="manager",
            latency_ms=outcome.latency_ms,
            **self._trace_kwargs(ctx),
            mode=mode,
            tasks=len(results),
            ok=outcome.ok_count,
            merged_chars=len(outcome.merged_text),
            patches=len(patches),
        )
        return outcome

    def _run_parallel(
        self,
        plan: ExecutionPlan,
        ordered: list[IntentItem],
        ctx: OrchestrationContext,
        *,
        stop_event: threading.Event | None,
        events: list[dict[str, Any]],
    ) -> list[SubAgentResult]:
        """按依赖分层并行：同层无依赖任务并发，跨层串行。"""
        results: dict[str, SubAgentResult] = {}
        pending = list(ordered)
        lock = threading.Lock()
        while pending:
            ready = [
                task
                for task in pending
                if all(dep in results or dep not in {item.task_id for item in pending} for dep in task.depends_on)
            ]
            if not ready:
                ready = list(pending)
            batch = ready[: max(self.max_parallel, plan.max_parallel)]
            if len(batch) == 1:
                task = batch[0]
                results[task.task_id] = self._dispatch(task, ctx, stop_event=stop_event, events=events)
            else:
                with ThreadPoolExecutor(max_workers=len(batch)) as pool:
                    futures = {
                        pool.submit(self._dispatch, task, ctx, stop_event=stop_event, events=events): task
                        for task in batch
                    }
                    for future, task in futures.items():
                        with lock:
                            results[task.task_id] = future.result()
            pending = [task for task in pending if task.task_id not in results]
            if stop_event is not None and stop_event.is_set():
                for task in pending:
                    results[task.task_id] = SubAgentResult(
                        task_id=task.task_id, skill=task.skill, status="cancelled"
                    )
                break
        return [results[task.task_id] for task in ordered if task.task_id in results]