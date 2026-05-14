"""Realtime/full-duplex event definitions and a small in-process event bus."""

from __future__ import annotations

import queue
import time
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class BaseRealtimeEvent:
    event_type: str
    ts: float = field(default_factory=time.time)
    turn_id: int | None = None

    def to_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["type"] = payload.pop("event_type")
        return payload


@dataclass(frozen=True)
class AudioInEvent(BaseRealtimeEvent):
    size_bytes: int = 0

    def __init__(self, size_bytes: int, turn_id: int | None = None, ts: float | None = None):
        object.__setattr__(self, "event_type", "audio_in")
        object.__setattr__(self, "ts", time.time() if ts is None else ts)
        object.__setattr__(self, "turn_id", turn_id)
        object.__setattr__(self, "size_bytes", int(size_bytes))


@dataclass(frozen=True)
class AsrPartialEvent(BaseRealtimeEvent):
    text: str = ""
    stability: float | None = None
    start_ms: int | None = None
    end_ms: int | None = None

    def __init__(
            self,
            text: str,
            stability: float | None = None,
            start_ms: int | None = None,
            end_ms: int | None = None,
            turn_id: int | None = None,
            ts: float | None = None,
    ):
        object.__setattr__(self, "event_type", "asr_partial")
        object.__setattr__(self, "ts", time.time() if ts is None else ts)
        object.__setattr__(self, "turn_id", turn_id)
        object.__setattr__(self, "text", text)
        object.__setattr__(self, "stability", stability)
        object.__setattr__(self, "start_ms", start_ms)
        object.__setattr__(self, "end_ms", end_ms)


@dataclass(frozen=True)
class AsrFinalEvent(BaseRealtimeEvent):
    text: str = ""
    stability: float | None = None
    start_ms: int | None = None
    end_ms: int | None = None
    attachments: list[dict[str, Any]] = field(default_factory=list)

    def __init__(
            self,
            text: str,
            stability: float | None = None,
            start_ms: int | None = None,
            end_ms: int | None = None,
            attachments: list[dict[str, Any]] | None = None,
            turn_id: int | None = None,
            ts: float | None = None,
    ):
        object.__setattr__(self, "event_type", "asr_final")
        object.__setattr__(self, "ts", time.time() if ts is None else ts)
        object.__setattr__(self, "turn_id", turn_id)
        object.__setattr__(self, "text", text)
        object.__setattr__(self, "stability", stability)
        object.__setattr__(self, "start_ms", start_ms)
        object.__setattr__(self, "end_ms", end_ms)
        object.__setattr__(self, "attachments", attachments or [])


@dataclass(frozen=True)
class StateChangedEvent(BaseRealtimeEvent):
    state: str = ""
    detail: str = ""

    def __init__(self, state: str, detail: str = "", turn_id: int | None = None, ts: float | None = None):
        object.__setattr__(self, "event_type", "state")
        object.__setattr__(self, "ts", time.time() if ts is None else ts)
        object.__setattr__(self, "turn_id", turn_id)
        object.__setattr__(self, "state", state)
        object.__setattr__(self, "detail", detail)


@dataclass(frozen=True)
class RouteDecisionEvent(BaseRealtimeEvent):
    session_scene: str = ""
    turn_scene: str = ""
    confidence: float = 0.0
    handler: str = ""
    strategy_id: str = ""
    delivery_mode: str = ""
    ui_mode: str = ""

    def __init__(
            self,
            session_scene: str,
            turn_scene: str,
            confidence: float,
            handler: str,
            strategy_id: str = "",
            delivery_mode: str = "",
            ui_mode: str = "",
            turn_id: int | None = None,
            ts: float | None = None,
    ):
        object.__setattr__(self, "event_type", "route")
        object.__setattr__(self, "ts", time.time() if ts is None else ts)
        object.__setattr__(self, "turn_id", turn_id)
        object.__setattr__(self, "session_scene", session_scene)
        object.__setattr__(self, "turn_scene", turn_scene)
        object.__setattr__(self, "confidence", float(confidence))
        object.__setattr__(self, "handler", handler)
        object.__setattr__(self, "strategy_id", strategy_id)
        object.__setattr__(self, "delivery_mode", delivery_mode)
        object.__setattr__(self, "ui_mode", ui_mode)


@dataclass(frozen=True)
class ContextDebugEvent(BaseRealtimeEvent):
    multimodal_summary: str = ""
    artifacts: list[dict[str, Any]] = field(default_factory=list)

    def __init__(
            self,
            multimodal_summary: str,
            artifacts: list[dict[str, Any]],
            turn_id: int | None = None,
            ts: float | None = None,
    ):
        object.__setattr__(self, "event_type", "debug_context")
        object.__setattr__(self, "ts", time.time() if ts is None else ts)
        object.__setattr__(self, "turn_id", turn_id)
        object.__setattr__(self, "multimodal_summary", multimodal_summary)
        object.__setattr__(self, "artifacts", artifacts)


@dataclass(frozen=True)
class PromptDebugEvent(BaseRealtimeEvent):
    handler: str = ""
    system_prompt: str = ""
    strategy_id: str = ""
    render_template: str = ""
    delivery_mode: str = ""
    ui_mode: str = ""

    def __init__(
            self,
            handler: str,
            system_prompt: str,
            strategy_id: str = "",
            render_template: str = "",
            delivery_mode: str = "",
            ui_mode: str = "",
            turn_id: int | None = None,
            ts: float | None = None,
    ):
        object.__setattr__(self, "event_type", "debug_prompt")
        object.__setattr__(self, "ts", time.time() if ts is None else ts)
        object.__setattr__(self, "turn_id", turn_id)
        object.__setattr__(self, "handler", handler)
        object.__setattr__(self, "system_prompt", system_prompt)
        object.__setattr__(self, "strategy_id", strategy_id)
        object.__setattr__(self, "render_template", render_template)
        object.__setattr__(self, "delivery_mode", delivery_mode)
        object.__setattr__(self, "ui_mode", ui_mode)


@dataclass(frozen=True)
class StrategyDebugEvent(BaseRealtimeEvent):
    branch: str = ""
    strategy_id: str = ""
    strategy_name: str = ""
    strategy_source: str = ""
    render_template: str = ""
    delivery_mode: str = ""
    ui_mode: str = ""
    user_followup_type: str = ""
    artifact_subject_hint: str = ""
    artifact_task_hint: str = ""
    artifact_text: str = ""

    def __init__(
            self,
            branch: str,
            strategy_id: str,
            strategy_name: str,
            strategy_source: str,
            render_template: str,
            delivery_mode: str,
            ui_mode: str,
            user_followup_type: str,
            artifact_subject_hint: str = "",
            artifact_task_hint: str = "",
            artifact_text: str = "",
            turn_id: int | None = None,
            ts: float | None = None,
    ):
        object.__setattr__(self, "event_type", "debug_strategy")
        object.__setattr__(self, "ts", time.time() if ts is None else ts)
        object.__setattr__(self, "turn_id", turn_id)
        object.__setattr__(self, "branch", branch)
        object.__setattr__(self, "strategy_id", strategy_id)
        object.__setattr__(self, "strategy_name", strategy_name)
        object.__setattr__(self, "strategy_source", strategy_source)
        object.__setattr__(self, "render_template", render_template)
        object.__setattr__(self, "delivery_mode", delivery_mode)
        object.__setattr__(self, "ui_mode", ui_mode)
        object.__setattr__(self, "user_followup_type", user_followup_type)
        object.__setattr__(self, "artifact_subject_hint", artifact_subject_hint)
        object.__setattr__(self, "artifact_task_hint", artifact_task_hint)
        object.__setattr__(self, "artifact_text", artifact_text)


@dataclass(frozen=True)
class MetricsDebugEvent(BaseRealtimeEvent):
    asr_final_latency_ms: float | None = None
    first_token_latency_ms: float | None = None
    first_audio_latency_ms: float | None = None
    interrupt_count: int = 0
    timeline_ms: dict[str, float | None] = field(default_factory=dict)

    def __init__(
            self,
            asr_final_latency_ms: float | None = None,
            first_token_latency_ms: float | None = None,
            first_audio_latency_ms: float | None = None,
            interrupt_count: int = 0,
            timeline_ms: dict[str, float | None] | None = None,
            turn_id: int | None = None,
            ts: float | None = None,
    ):
        object.__setattr__(self, "event_type", "debug_metrics")
        object.__setattr__(self, "ts", time.time() if ts is None else ts)
        object.__setattr__(self, "turn_id", turn_id)
        object.__setattr__(self, "asr_final_latency_ms", asr_final_latency_ms)
        object.__setattr__(self, "first_token_latency_ms", first_token_latency_ms)
        object.__setattr__(self, "first_audio_latency_ms", first_audio_latency_ms)
        object.__setattr__(self, "interrupt_count", int(interrupt_count))
        object.__setattr__(self, "timeline_ms", dict(timeline_ms or {}))


@dataclass(frozen=True)
class AssistantTokenEvent(BaseRealtimeEvent):
    token: str = ""

    def __init__(self, token: str, turn_id: int | None = None, ts: float | None = None):
        object.__setattr__(self, "event_type", "assistant_token")
        object.__setattr__(self, "ts", time.time() if ts is None else ts)
        object.__setattr__(self, "turn_id", turn_id)
        object.__setattr__(self, "token", token)


@dataclass(frozen=True)
class AssistantCompletedEvent(BaseRealtimeEvent):
    text: str = ""
    interrupted: bool = False

    def __init__(self, text: str, interrupted: bool, turn_id: int | None = None, ts: float | None = None):
        object.__setattr__(self, "event_type", "assistant_completed")
        object.__setattr__(self, "ts", time.time() if ts is None else ts)
        object.__setattr__(self, "turn_id", turn_id)
        object.__setattr__(self, "text", text)
        object.__setattr__(self, "interrupted", bool(interrupted))


@dataclass(frozen=True)
class TtsChunkEvent(BaseRealtimeEvent):
    bytes_len: int = 0
    sample_rate: int | None = None
    pcm_base64: str | None = None

    def __init__(
            self,
            bytes_len: int,
            turn_id: int | None = None,
            ts: float | None = None,
            sample_rate: int | None = None,
            pcm_base64: str | None = None,
    ):
        object.__setattr__(self, "event_type", "tts_chunk")
        object.__setattr__(self, "ts", time.time() if ts is None else ts)
        object.__setattr__(self, "turn_id", turn_id)
        object.__setattr__(self, "bytes_len", int(bytes_len))
        object.__setattr__(self, "sample_rate", sample_rate)
        object.__setattr__(self, "pcm_base64", pcm_base64)


@dataclass(frozen=True)
class ControlEvent(BaseRealtimeEvent):
    action: str = ""
    detail: str = ""

    def __init__(self, action: str, detail: str = "", turn_id: int | None = None, ts: float | None = None):
        object.__setattr__(self, "event_type", "control")
        object.__setattr__(self, "ts", time.time() if ts is None else ts)
        object.__setattr__(self, "turn_id", turn_id)
        object.__setattr__(self, "action", action)
        object.__setattr__(self, "detail", detail)


@dataclass(frozen=True)
class ErrorEvent(BaseRealtimeEvent):
    scope: str = ""
    message: str = ""

    def __init__(self, scope: str, message: str, turn_id: int | None = None, ts: float | None = None):
        object.__setattr__(self, "event_type", "error")
        object.__setattr__(self, "ts", time.time() if ts is None else ts)
        object.__setattr__(self, "turn_id", turn_id)
        object.__setattr__(self, "scope", scope)
        object.__setattr__(self, "message", message)


class RealtimeEventBus:
    """Thread-safe queue used by session runtime and UI transports."""

    def __init__(self, maxsize: int = 2048) -> None:
        self._queue: queue.Queue[BaseRealtimeEvent] = queue.Queue(maxsize=maxsize)

    def publish(self, event: BaseRealtimeEvent) -> None:
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            try:
                _ = self._queue.get_nowait()
            except queue.Empty:
                return
            try:
                self._queue.put_nowait(event)
            except queue.Full:
                return

    def drain(self, max_items: int = 64) -> list[BaseRealtimeEvent]:
        events: list[BaseRealtimeEvent] = []
        for _ in range(max_items):
            try:
                events.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return events

    def drop_turn_events(self, turn_id: int, event_types: set[str] | tuple[str, ...]) -> None:
        kept: list[BaseRealtimeEvent] = []
        blocked = set(event_types)
        while True:
            try:
                event = self._queue.get_nowait()
            except queue.Empty:
                break
            if event.turn_id == turn_id and event.event_type in blocked:
                continue
            kept.append(event)
        for event in kept:
            self.publish(event)
