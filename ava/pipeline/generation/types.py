"""生成流水线旧类型导出层。

这里不再维护独立的 `TurnPlan` 实现。
正式类型唯一来源是 `ava.inference_runtime.types`。
"""

from ava.inference_runtime.types import TurnPlan

__all__ = ["TurnPlan"]
