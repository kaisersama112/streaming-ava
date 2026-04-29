"""Route decision schema shared across router and orchestrators."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

SessionScene = Literal["education", "general"]
TurnScene = Literal["education", "general_qa", "casual_chat", "clarify"]


class RouteDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_scene: SessionScene = Field(...)
    turn_scene: TurnScene = Field(...)
    intent: str = Field(...)
    confidence: float = Field(...)
    should_preserve_teaching_state: bool = Field(...)
    need_clarification: bool = Field(...)

    @field_validator("confidence")
    @classmethod
    def clamp_confidence(cls, value: float) -> float:
        if value < 0:
            return 0.0
        if value > 1:
            return 1.0
        return value
