"""子 Agent 协作协议类型（强校验，替代裸 dict 计划）。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

SkillName = str
TaskStatus = Literal["ok", "error", "skipped", "cancelled"]
OrchestrationMode = Literal["serial", "parallel", "conditional"]


class IntentItem(BaseModel):
    """一个可独立执行的技能子任务。"""

    task_id: str = ""
    skill: SkillName
    priority: int = 100
    confidence: float = 0.0
    params: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)
    condition: str = ""

    @field_validator("skill")
    @classmethod
    def _normalize_skill(cls, value: str) -> str:
        normalized = str(value or "").strip().replace("_", "-")
        if not normalized:
            raise ValueError("skill 不能为空")
        return normalized

    @field_validator("confidence")
    @classmethod
    def _clamp_confidence(cls, value: float) -> float:
        return max(0.0, min(1.0, float(value or 0.0)))


class ExecutionPlan(BaseModel):
    """一轮内的子任务编排计划。"""

    mode: OrchestrationMode = "serial"
    tasks: list[IntentItem] = Field(default_factory=list)
    merge: Literal["concat", "primary"] = "concat"
    max_parallel: int = 3

    @field_validator("max_parallel")
    @classmethod
    def _clamp_parallel(cls, value: int) -> int:
        return max(1, min(8, int(value or 1)))

    def ordered_tasks(self) -> list[IntentItem]:
        """按依赖拓扑 + 优先级排序，忽略悬空依赖。"""
        remaining = list(self.tasks)
        resolved: set[str] = set()
        ordered: list[IntentItem] = []
        while remaining:
            ready = [
                task
                for task in remaining
                if all(dep in resolved for dep in task.depends_on if dep)
            ]
            if not ready:
                ready = list(remaining)
            ready.sort(key=lambda item: (item.priority, item.task_id))
            picked = ready[0]
            ordered.append(picked)
            resolved.add(picked.task_id)
            remaining.remove(picked)
        return ordered


class SubAgentResult(BaseModel):
    """子 Agent 执行结果。"""

    task_id: str = ""
    skill: str = ""
    status: TaskStatus = "ok"
    text: str = ""
    patches: list[dict[str, Any]] = Field(default_factory=list)
    latency_ms: float = 0.0
    error: str = ""
    events: list[dict[str, Any]] = Field(default_factory=list)


class OrchestrationOutcome(BaseModel):
    """编排汇总：合并回复 + 待应用 patch + 事件轨迹。"""

    mode: OrchestrationMode = "serial"
    results: list[SubAgentResult] = Field(default_factory=list)
    merged_text: str = ""
    patches: list[dict[str, Any]] = Field(default_factory=list)
    events: list[dict[str, Any]] = Field(default_factory=list)
    latency_ms: float = 0.0

    @property
    def ok_count(self) -> int:
        return sum(1 for item in self.results if item.status == "ok")