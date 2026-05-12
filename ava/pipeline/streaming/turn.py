"""Realtime turn control primitives."""

from __future__ import annotations

import enum
import threading
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ava.pipeline.streaming.voice_stream import StreamingVoicePipeline
    from ava.interfaces.websocket import RealtimeAudioBridge


class TurnStatus(str, enum.Enum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    INTERRUPTING = "interrupting"
    SHUTDOWN = "shutdown"


@dataclass
class TurnControl:
    """Control surface for stopping an in-flight turn quickly."""

    turn_id: int
    stop_event: threading.Event
    bridge: "RealtimeAudioBridge"
    user_text: str = ""
    tts_pipeline: "StreamingVoicePipeline | None" = None
    status: TurnStatus = TurnStatus.IDLE
    interrupted: bool = False
    assistant_text: str = ""
    started_at: float = field(default_factory=time.monotonic)
    finished_at: float | None = None
    asr_final_at: float | None = None
    asr_final_latency_ms: float | None = None
    first_token_at: float | None = None
    first_audio_at: float | None = None
    t0_submit_at: float | None = None
    t1_prepare_state_done_at: float | None = None
    t2_router_done_at: float | None = None
    t3_turn_plan_done_at: float | None = None
    t4_first_token_at: float | None = None
    t5_first_tts_submit_at: float | None = None
    t6_first_tts_chunk_at: float | None = None
    t7_first_push_pcm_at: float | None = None
    worker_thread: threading.Thread | None = None
    pump_thread: threading.Thread | None = None
    pump_metrics: dict[str, Any] = field(default_factory=dict)

    def interrupt(self) -> None:
        """Best-effort immediate stop for LLM/TTS/pump/playback."""
        self.interrupted = True
        self.status = TurnStatus.INTERRUPTING
        try:
            self.stop_event.set()
        except Exception:
            pass
        if self.tts_pipeline is not None:
            try:
                self.tts_pipeline.interrupt()
            except Exception:
                pass
        try:
            self.bridge.flush()
        except Exception:
            pass

