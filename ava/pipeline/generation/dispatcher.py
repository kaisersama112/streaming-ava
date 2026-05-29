"""兼容层：转发到新的 turn planner 实现。"""

from __future__ import annotations

from ava.inference_runtime.turn_planner import build_turn_plan

__all__ = ["build_turn_plan"]
