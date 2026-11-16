"""Router / Responder / Manager / 技能子 Agent 之间的消息信封协议。

所有跨 Agent 通信都用统一信封，带 correlation_id + seq，便于 trace 回放：
- task.assign   Manager → 技能子 Agent
- task.result   技能子 Agent → Manager
- task.error    技能子 Agent → Manager
- state.patch   技能子 Agent → 状态白名单写入点（建议，非直接写入）
- control.cancel Manager → 技能子 Agent（barge-in / 超时）
"""

from __future__ import annotations

import itertools
import threading
from typing import Any, Literal

from pydantic import BaseModel, Field

EnvelopeType = Literal["task.assign", "task.result", "task.error", "state.patch", "control.cancel"]

_SEQ_LOCK = threading.Lock()
_SEQ = itertools.count(1)


def next_seq() -> int:
    with _SEQ_LOCK:
        return next(_SEQ)


class Envelope(BaseModel):
    """统一协作信封。"""

    type: EnvelopeType
    correlation_id: str
    seq: int = Field(default_factory=next_seq)
    session_id: str = ""
    turn_id: int | None = None
    trace_id: str = ""
    sender: str = ""
    receiver: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def _envelope(
    type_: EnvelopeType,
    *,
    correlation_id: str,
    sender: str,
    receiver: str,
    payload: dict[str, Any] | None = None,
    session_id: str = "",
    turn_id: int | None = None,
    trace_id: str = "",
) -> Envelope:
    return Envelope(
        type=type_,
        correlation_id=str(correlation_id or ""),
        session_id=session_id,
        turn_id=turn_id,
        trace_id=trace_id,
        sender=sender,
        receiver=receiver,
        payload=dict(payload or {}),
    )


def task_assign(task: Any, **kwargs: Any) -> Envelope:
    return _envelope(
        "task.assign",
        sender="manager",
        receiver=f"skill:{getattr(task, 'skill', '')}",
        payload={"task": task.model_dump(mode="json") if hasattr(task, "model_dump") else dict(task or {})},
        **kwargs,
    )


def task_result(result: Any, **kwargs: Any) -> Envelope:
    return _envelope(
        "task.result",
        sender=f"skill:{getattr(result, 'skill', '')}",
        receiver="manager",
        payload={"result": result.model_dump(mode="json") if hasattr(result, "model_dump") else dict(result or {})},
        **kwargs,
    )


def task_error(task_id: str, skill: str, error: str, **kwargs: Any) -> Envelope:
    return _envelope(
        "task.error",
        sender=f"skill:{skill}",
        receiver="manager",
        payload={"task_id": task_id, "skill": skill, "error": str(error or "")},
        **kwargs,
    )


def state_patch(patches: list[dict[str, Any]], *, actor: str = "skill", **kwargs: Any) -> Envelope:
    return _envelope(
        "state.patch",
        sender=actor,
        receiver="state_whitelist",
        payload={"patches": list(patches or [])},
        **kwargs,
    )


def control_cancel(reason: str = "interrupted", **kwargs: Any) -> Envelope:
    return _envelope(
        "control.cancel",
        sender="manager",
        receiver="skills",
        payload={"reason": str(reason or "")},
        **kwargs,
    )