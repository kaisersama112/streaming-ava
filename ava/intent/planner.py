"""从 Router 计划推导子 Agent 编排计划。"""

from __future__ import annotations

from typing import Any

from ava.intent.skills import EDUCATION_SKILLS
from ava.intent.types import ExecutionPlan, IntentItem

_MODULE_SKILL_ALIASES = {
    "solve": "solve",
    "check": "check",
    "explain": "explain",
    "assess": "assess",
    "answer": "solve",
    "qa": "explain",
}


def _normalize_skill(name: str) -> str:
    value = str(name or "").strip().replace("_", "-")
    return _MODULE_SKILL_ALIASES.get(value, value)


def build_execution_plan(
    *,
    decision: Any,
    router_plan: dict[str, Any] | None,
    mode: str = "serial",
    max_parallel: int = 3,
) -> ExecutionPlan:
    """把 router_plan（module / secondary_actions / intents）翻译成子任务计划。

    - 单意图：一个主任务
    - 多意图：router_plan.intents 列表，或 module + secondary_actions
    - 条件分支：assess 默认挂 previous_ok（批改/解题成功后才评估）
    """
    plan = dict(router_plan or {})
    turn_scene = str(getattr(decision, "turn_scene", "") or "")
    confidence = float(getattr(decision, "confidence", 0.0) or 0.0)
    raw_intents = list(plan.get("intents") or [])

    tasks: list[IntentItem] = []
    if raw_intents:
        for index, item in enumerate(raw_intents):
            entry = dict(item or {}) if isinstance(item, dict) else {"skill": str(item)}
            skill = _normalize_skill(entry.get("skill") or entry.get("module") or entry.get("intent") or "")
            if not skill:
                continue
            tasks.append(
                IntentItem(
                    task_id=str(entry.get("task_id") or f"t{index + 1}_{skill}"),
                    skill=skill,
                    priority=int(entry.get("priority", (index + 1) * 10) or 0),
                    confidence=float(entry.get("confidence", confidence) or 0.0),
                    params=dict(entry.get("params") or {}),
                    depends_on=[str(dep) for dep in list(entry.get("depends_on") or []) if str(dep).strip()],
                    condition=str(entry.get("condition") or "").strip(),
                )
            )
    else:
        primary = _normalize_skill(plan.get("module") or plan.get("mode") or "")
        if turn_scene == "education" and primary in EDUCATION_SKILLS:
            tasks.append(
                IntentItem(
                    task_id=f"t1_{primary}",
                    skill=primary,
                    priority=10,
                    confidence=confidence,
                    params={
                        key: plan[key]
                        for key in ("subject", "pedagogy", "learning_objects", "answer_boundary")
                        if plan.get(key)
                    },
                )
            )
            for index, action in enumerate(list(plan.get("secondary_actions") or [])):
                skill = _normalize_skill(action)
                if not skill or skill == primary:
                    continue
                tasks.append(
                    IntentItem(
                        task_id=f"t{index + 2}_{skill}",
                        skill=skill,
                        priority=20 + index * 10,
                        confidence=confidence,
                        depends_on=[f"t1_{primary}"],
                        condition="previous_ok" if skill == "assess" else "",
                    )
                )

    if not tasks:
        return ExecutionPlan(mode="serial", tasks=[], merge="concat", max_parallel=max_parallel)

    selected_mode = mode if mode in {"serial", "parallel", "conditional"} else "serial"
    if selected_mode == "serial" and any(task.condition for task in tasks):
        selected_mode = "conditional"
    return ExecutionPlan(mode=selected_mode, tasks=tasks, merge="concat", max_parallel=max_parallel)