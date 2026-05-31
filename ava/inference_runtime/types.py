"""推理运行时核心类型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class TurnPlan:
    """当前轮执行计划。"""

    decision: Any
    orchestrator_name: str
    strategy: Any | None
    instructions: str
    input: list[dict[str, object]]
    model: str = ""
    router_plan: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
