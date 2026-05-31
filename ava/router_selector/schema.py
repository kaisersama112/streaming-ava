"""路由结果结构。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class RouteDecision(BaseModel):
    """当前轮路由决策。"""

    session_scene: str = Field(default="general")
    turn_scene: str = Field(default="general_qa")
    intent: str = Field(default="")
    confidence: float = Field(default=0.0)
    should_preserve_teaching_state: bool = Field(default=False)
    need_clarification: bool = Field(default=False)
