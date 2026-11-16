"""编排器：串行 / 并行 / 条件分支 + 协议信封 + 取消。"""

from __future__ import annotations

import threading
import time

from ava.intent.orchestrator import OrchestrationContext, SkillOrchestrator
from ava.intent.planner import build_execution_plan
from ava.intent.types import ExecutionPlan, IntentItem, SubAgentResult
from ava.router_selector.schema import RouteDecision


class StubRunner:
    """离线测试用技能执行器。"""

    def __init__(self, *, delay: float = 0.0, fail_skills: set[str] | None = None):
        self.delay = delay
        self.fail_skills = fail_skills or set()
        self.calls: list[str] = []
        self.parallel_seen = 0

    def __call__(self, task, ctx, *, stop_event=None):
        self.calls.append(task.skill)
        if self.delay:
            time.sleep(self.delay)
        if stop_event is not None and stop_event.is_set():
            return SubAgentResult(task_id=task.task_id, skill=task.skill, status="cancelled")
        if task.skill in self.fail_skills:
            raise RuntimeError(f"{task.skill} failed")
        return SubAgentResult(
            task_id=task.task_id,
            skill=task.skill,
            status="ok",
            text=f"[{task.skill}] 结果",
            patches=[{"key": "knowledge_point", "value": f"{task.skill}-kp", "reason": "test"}],
        )


def _decision(**kwargs):
    base = dict(
        session_scene="education",
        turn_scene="education",
        intent="solve",
        confidence=0.9,
        should_preserve_teaching_state=True,
    )
    base.update(kwargs)
    return RouteDecision(**base)


def _ctx():
    return OrchestrationContext(
        session_id="s",
        turn_id=1,
        trace_id="tr",
        user_message={"role": "user", "content": [{"type": "input_text", "text": "解这道题"}]},
    )


def test_serial_order_and_merge():
    plan = ExecutionPlan(
        mode="serial",
        tasks=[
            IntentItem(task_id="b", skill="explain", priority=20),
            IntentItem(task_id="a", skill="solve", priority=10),
        ],
    )
    runner = StubRunner()
    outcome = SkillOrchestrator(runner=runner).run(plan, _ctx())
    assert runner.calls == ["solve", "explain"]
    assert outcome.merged_text == "[solve] 结果\n\n[explain] 结果"
    assert len(outcome.patches) == 2
    assert outcome.ok_count == 2


def test_parallel_runs_independent_tasks_concurrently():
    plan = ExecutionPlan(
        mode="parallel",
        tasks=[
            IntentItem(task_id="a", skill="solve", priority=10),
            IntentItem(task_id="b", skill="explain", priority=20),
        ],
        max_parallel=2,
    )
    runner = StubRunner(delay=0.2)
    started = time.monotonic()
    outcome = SkillOrchestrator(runner=runner).run(plan, _ctx())
    elapsed = time.monotonic() - started
    assert outcome.ok_count == 2
    assert elapsed < 0.35, f"并行未生效: {elapsed:.3f}s"


def test_conditional_branch_skips_when_predicate_false():
    plan = ExecutionPlan(
        mode="conditional",
        tasks=[
            IntentItem(task_id="a", skill="check", priority=10),
            IntentItem(task_id="b", skill="assess", priority=20, depends_on=["a"], condition="previous_ok"),
        ],
    )
    runner = StubRunner(fail_skills={"check"})
    outcome = SkillOrchestrator(runner=runner).run(plan, _ctx())
    statuses = {item.skill: item.status for item in outcome.results}
    assert statuses["check"] == "error"
    assert statuses["assess"] == "skipped"
    assert "check" in outcome.merged_text or outcome.merged_text == ""


def test_conditional_branch_runs_when_predicate_true():
    plan = ExecutionPlan(
        mode="conditional",
        tasks=[
            IntentItem(task_id="a", skill="check", priority=10),
            IntentItem(task_id="b", skill="assess", priority=20, depends_on=["a"], condition="previous_ok"),
        ],
    )
    outcome = SkillOrchestrator(runner=StubRunner()).run(plan, _ctx())
    assert {item.skill: item.status for item in outcome.results} == {"check": "ok", "assess": "ok"}


def test_unknown_predicate_is_skipped_not_executed():
    plan = ExecutionPlan(
        mode="conditional",
        tasks=[IntentItem(task_id="a", skill="solve", condition="unregistered_dynamic_expression")],
    )
    runner = StubRunner()
    outcome = SkillOrchestrator(runner=runner).run(plan, _ctx())
    assert runner.calls == []
    assert outcome.results[0].status == "skipped"


def test_stop_event_cancels_remaining_tasks():
    plan = ExecutionPlan(
        mode="serial",
        tasks=[
            IntentItem(task_id="a", skill="solve", priority=10),
            IntentItem(task_id="b", skill="explain", priority=20),
        ],
    )
    stop = threading.Event()

    class CancelAfterFirst(StubRunner):
        def __call__(self, task, ctx, *, stop_event=None):
            result = super().__call__(task, ctx, stop_event=stop_event)
            stop.set()
            return result

    outcome = SkillOrchestrator(runner=CancelAfterFirst()).run(plan, _ctx(), stop_event=stop)
    assert outcome.results[0].status == "ok"
    assert outcome.results[1].status == "cancelled"
    # 已完成结果保留，用于未完成 turn 上下文
    assert "[solve] 结果" in outcome.merged_text


def test_protocol_envelopes_recorded():
    plan = ExecutionPlan(mode="serial", tasks=[IntentItem(task_id="a", skill="solve")])
    outcome = SkillOrchestrator(runner=StubRunner()).run(plan, _ctx())
    types = [event["type"] for event in outcome.events]
    assert "task.assign" in types
    assert "task.result" in types
    assert "state.patch" in types
    assert all(event["correlation_id"] for event in outcome.events)
    seqs = [event["seq"] for event in outcome.events]
    assert seqs == sorted(seqs)


def test_planner_from_router_plan_secondary_actions():
    plan = build_execution_plan(
        decision=_decision(),
        router_plan={"module": "check", "subject": "math", "secondary_actions": ["assess"]},
        mode="serial",
    )
    assert [task.skill for task in plan.tasks] == ["check", "assess"]
    assert plan.mode == "conditional"
    assert plan.tasks[1].condition == "previous_ok"
    assert plan.tasks[1].depends_on == ["t1_check"]


def test_planner_multi_intent_list():
    plan = build_execution_plan(
        decision=_decision(),
        router_plan={
            "intents": [
                {"skill": "solve", "priority": 10},
                {"skill": "explain", "priority": 20, "depends_on": ["t1_solve"]},
            ]
        },
        mode="parallel",
    )
    assert plan.mode == "parallel"
    assert [task.task_id for task in plan.ordered_tasks()] == ["t1_solve", "t2_explain"]


def test_planner_general_scene_has_no_education_tasks():
    plan = build_execution_plan(
        decision=_decision(turn_scene="general_qa", session_scene="general"),
        router_plan={"mode": "fact"},
    )
    assert plan.tasks == []