"""Session-scoped full-duplex runtime."""

from __future__ import annotations

import base64
from difflib import SequenceMatcher
import logging
import threading
import time
from typing import Any

from ava.application.conversation import load_state, prepare_state_for_turn
from ava.application.evaluation import build_evaluation_tags
from ava.application.factories import build_prompt_center, build_router
from ava.application.multimodal import AttachmentPayload, build_turn_input
from ava.application.orchestration import build_turn_plan
from ava.application.responding import stream_reply_with_callbacks
from ava.application.speech import LatexAwareSpeechBuffer, should_apply_math_oralizer
from ava.application.trace import append_trace_log, sanitize_turn_input, sanitize_value
from ava.application.realtime.barge_in import BargeInConfig, BargeInDetector
from ava.application.realtime.events import (
    AsrFinalEvent,
    AsrPartialEvent,
    AssistantCompletedEvent,
    AssistantTokenEvent,
    AudioInEvent,
    ControlEvent,
    ContextDebugEvent,
    ErrorEvent,
    MetricsDebugEvent,
    PromptDebugEvent,
    RealtimeEventBus,
    RouteDecisionEvent,
    StateChangedEvent,
    StrategyDebugEvent,
    TtsChunkEvent,
)
from ava.application.realtime.turn import TurnControl, TurnStatus
from ava.application.voice_stream import StreamingVoicePipeline, VoiceStreamConfig
from ava.domain.context import MediaArtifact, TurnInput, assemble_context
from ava.domain.session.state import ConversationState
from ava.infrastructure.realtime import RealtimeAudioBridge
from ava.infrastructure.tts.streaming_sdk import CosyVoiceSDKError
from config import settings

_LOG = logging.getLogger("streaming_ava.realtime.session")


def _compact_snapshot_trace(snapshot: Any) -> dict[str, Any]:
    return {
        "session_id": getattr(snapshot, "session_id", ""),
        "context_profile": getattr(snapshot, "context_profile", ""),
        "user_text": getattr(snapshot, "user_text", ""),
        "session_scene": getattr(snapshot, "session_scene", ""),
        "turn_scene": getattr(snapshot, "turn_scene", ""),
        "recent_history_summary_len": len(str(getattr(snapshot, "recent_history_summary", "") or "")),
        "recent_turns_summary_len": len(str(getattr(snapshot, "recent_turns_summary", "") or "")),
        "history_messages_count": len(getattr(snapshot, "history_messages", []) or []),
        "artifacts_count": len(getattr(snapshot, "artifacts", ()) or ()),
        "reference_artifacts_count": len(getattr(snapshot, "reference_artifacts", ()) or ()),
    }


def _compact_debug_prompt(text: str, limit: int = 1200) -> str:
    value = str(text or "").strip()
    if len(value) <= limit:
        return value
    return f"{value[:limit].rstrip()}…"


def _artifact_to_payload(artifact: MediaArtifact, *, include_inline_data: bool = False) -> dict[str, Any]:
    payload = artifact.to_prompt_dict()
    if artifact.uri:
        payload["uri"] = artifact.uri
    if include_inline_data and artifact.data_url and artifact.kind in {"image", "audio", "video"}:
        payload["data_url"] = artifact.data_url
    return payload


def _artifacts_to_payload(turn_input: TurnInput, *, include_inline_data: bool = False) -> list[dict[str, Any]]:
    return [_artifact_to_payload(artifact, include_inline_data=include_inline_data) for artifact in
            turn_input.artifacts]


def _message_content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                text = str(block.get("text", "")).strip()
                if text:
                    parts.append(text)
                    continue
            for key in ("image_url", "input_audio", "video"):
                if key in block:
                    parts.append(f"[{key}]")
                    break
        return "\n".join(parts).strip()
    return str(content or "")


class RealtimeConversationSession:
    """Conversation runtime for full-duplex voice sessions."""

    def __init__(
            self,
            bridge: RealtimeAudioBridge,
            *,
            state: ConversationState | None = None,
            history_window: int | None = None,
            max_context_messages: int | None = None,
            session_id: str | None = None,
    ) -> None:
        self.bridge = bridge
        self.session_id = ConversationState.normalize_session_id(session_id or settings.runtime.default_session_id)
        self.state = state or load_state(
            settings.runtime.state_file,
            settings.runtime.history_window,
            session_id=self.session_id,
        )
        self.session_id = self.state.session_id
        self.history_window = history_window or settings.runtime.history_window
        self.max_context_messages = max_context_messages or settings.runtime.max_context_messages
        self.prompt_center = build_prompt_center()
        self.router = build_router(self.prompt_center)
        self.events = RealtimeEventBus()
        self._lock = threading.RLock()
        self._active: TurnControl | None = None
        self._turn_seq = 0
        self._shutdown = threading.Event()
        self._session_status = TurnStatus.LISTENING
        self._barge_in = BargeInDetector(
            BargeInConfig(
                min_partial_chars=int(getattr(settings.runtime, "barge_in_partial_chars", 2) or 2),
                stability_threshold=float(getattr(settings.runtime, "barge_in_stability_threshold", 0.35) or 0.35),
                cooldown_ms=int(getattr(settings.runtime, "barge_in_cooldown_ms", 450) or 450),
            )
        )
        self._interrupt_count = 0
        self._last_audio_frame_ts: float | None = None
        self._last_tts_chunk_at: float = 0.0
        self._emit_state(TurnStatus.LISTENING, detail="session_ready")
        self._emit_metrics()

    def history_snapshot(self, limit: int = 12) -> list[dict[str, object]]:
        turns = self.state.turn_records[-max(0, limit):]
        payload: list[dict[str, object]] = []
        for index, record in enumerate(turns):
            turn_key = record.get("created_at") or f"history-{index}"
            decision = dict(record.get("decision") or {})
            strategy = dict(record.get("strategy") or {})
            evaluation = dict(record.get("evaluation") or {})
            turn_status = str(record.get("turn_status", "completed") or "completed")
            payload.append(
                {
                    "role": "user",
                    "key": f"{turn_key}-user",
                    "text": record.get("user_text") or record.get("multimodal_summary") or "",
                    "summary": record.get("multimodal_summary") or "",
                    "artifacts": record.get("artifacts") or [],
                    "created_at": record.get("created_at") or "",
                }
            )
            assistant_text = str(record.get("assistant_text") or "").strip()
            if not assistant_text and turn_status == "interrupted":
                assistant_text = "已中断"
            elif not assistant_text and turn_status == "error":
                assistant_text = "本轮未完成"
            elif not assistant_text and turn_status == "pending":
                assistant_text = "处理中"

            if assistant_text or strategy or evaluation or decision:
                payload.append(
                    {
                        "role": "assistant",
                        "key": f"{turn_key}-assistant",
                        "text": assistant_text,
                        "created_at": record.get("created_at") or "",
                        "intent": record.get("intent") or "",
                        "meta": {
                            "branch": evaluation.get("branch") or decision.get("turn_scene", ""),
                            "strategy_id": strategy.get("strategy_id", ""),
                            "strategy_name": strategy.get("name", ""),
                            "delivery_mode": evaluation.get("delivery_mode") or strategy.get("delivery_mode", ""),
                            "ui_mode": evaluation.get("ui_mode") or strategy.get("ui_mode", ""),
                            "user_followup_type": evaluation.get("user_followup_type", ""),
                            "render_template": strategy.get("render_template", ""),
                            "strategy_source": strategy.get("source", ""),
                            "turn_status": turn_status,
                        },
                    }
                )
        return payload

    @property
    def active(self) -> TurnControl | None:
        with self._lock:
            return self._active

    @property
    def status(self) -> TurnStatus:
        with self._lock:
            return self._session_status

    def begin_turn(self, user_text: str = "") -> TurnControl:
        # 如果有正在进行的轮次，先走完整打断流程（含 event drop + bridge rebuild）
        with self._lock:
            prev_active = self._active
        if prev_active is not None and not prev_active.stop_event.is_set():
            self.interrupt(reason="new_turn")
        with self._lock:
            self._turn_seq += 1
            ctrl = TurnControl(
                turn_id=self._turn_seq,
                stop_event=threading.Event(),
                bridge=self.bridge,
                user_text=user_text,
                status=TurnStatus.THINKING,
            )
            self._active = ctrl
            self._emit_state(TurnStatus.THINKING, turn_id=ctrl.turn_id, detail="turn_started")
            self.events.publish(ControlEvent(action="start_turn", detail=user_text[:80], turn_id=ctrl.turn_id))
            return ctrl

    def _preempt_active_turn_for_user_input(self, *, reason: str, detail: str = "") -> None:
        active = self.active
        if active is None:
            return
        if active.stop_event.is_set():
            return
        if active.status not in (TurnStatus.SPEAKING, TurnStatus.THINKING):
            return
        append_trace_log(
            "realtime.turn.preempted_by_user_input",
            {
                "reason": reason,
                "detail": detail[:120],
                "active_turn_id": active.turn_id,
                "active_status": active.status.value,
            },
            turn_id=active.turn_id,
            scope="realtime_turn",
        )
        self.interrupt(reason=reason)

    def attach_tts(self, ctrl: TurnControl, tts_pipeline: StreamingVoicePipeline | None) -> None:
        with self._lock:
            if self._active is not ctrl:
                return
            ctrl.tts_pipeline = tts_pipeline
            if tts_pipeline is not None:
                ctrl.status = TurnStatus.SPEAKING
                self._emit_state(TurnStatus.SPEAKING, turn_id=ctrl.turn_id, detail="tts_attached")

    def end_turn(self, ctrl: TurnControl) -> None:
        with self._lock:
            ctrl.finished_at = time.monotonic()
            if self._active is ctrl:
                self._active = None
                self._emit_state(TurnStatus.LISTENING, turn_id=ctrl.turn_id, detail="turn_finished")

    def on_audio_frame(self, frame: bytes, *, ts: float | None = None) -> None:
        if not frame:
            return
        frame_ts = time.monotonic() if ts is None else ts
        with self._lock:
            self._last_audio_frame_ts = frame_ts
        active = self.active
        self.events.publish(
            AudioInEvent(size_bytes=len(frame), turn_id=(active.turn_id if active else None), ts=frame_ts))

    def on_asr_partial(
            self,
            text: str,
            *,
            stability: float | None = None,
            start_ms: int | None = None,
            end_ms: int | None = None,
            ts: float | None = None,
    ) -> None:
        active = self.active
        if bool(getattr(settings.runtime, "trace_log_asr_partials", True)):
            append_trace_log(
                "realtime.asr.partial",
                {
                    "text": text,
                    "stability": stability,
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "active_turn_id": (active.turn_id if active else None),
                },
                turn_id=(active.turn_id if active else None),
                scope="realtime_asr",
            )
        if self._looks_like_playback_echo(text, active):
            self.events.publish(
                ControlEvent(
                    action="ignored_echo_partial",
                    detail=(text or "")[:80],
                    turn_id=(active.turn_id if active else None),
                )
            )
            return
        self.events.publish(
            AsrPartialEvent(
                text=text,
                stability=stability,
                start_ms=start_ms,
                end_ms=end_ms,
                turn_id=(active.turn_id if active else None),
                ts=ts,
            )
        )
        # 允许在 SPEAKING 或 THINKING 阶段触发 barge-in 打断
        _is_active = bool(
            active is not None
            and active.status in (TurnStatus.SPEAKING, TurnStatus.THINKING)
        )
        if self._barge_in.should_interrupt(
                text=text,
                stability=stability,
                is_speaking=_is_active,
        ):
            self._preempt_active_turn_for_user_input(reason="barge_in", detail=text)

    def on_asr_final(
            self,
            text: str,
            *,
            attachments: list[AttachmentPayload] | None = None,
            stability: float | None = None,
            start_ms: int | None = None,
            end_ms: int | None = None,
            ts: float | None = None,
            source: str = "realtime_web",
    ) -> int | None:
        normalized = " ".join((text or "").split()).strip()
        final_ts = time.monotonic() if ts is None else ts
        if self._shutdown.is_set():
            return None
        active = self.active
        if self._looks_like_playback_echo(normalized, active):
            self.events.publish(
                ControlEvent(
                    action="ignored_echo_final",
                    detail=normalized[:80],
                    turn_id=(active.turn_id if active else None),
                )
            )
            return None

        turn_input = build_turn_input(normalized, attachments=attachments, source=source)
        if not normalized and not turn_input.artifacts:
            return None

        # Final ASR input is an explicit user turn signal. Preempt the current
        # assistant turn immediately instead of waiting for the next turn setup.
        self._preempt_active_turn_for_user_input(
            reason="barge_in_final",
            detail=normalized or turn_input.multimodal_summary(),
        )

        asr_final_latency_ms: float | None = None
        with self._lock:
            if self._last_audio_frame_ts is not None:
                asr_final_latency_ms = max(0.0, (final_ts - self._last_audio_frame_ts) * 1000.0)

        self.events.publish(
            AsrFinalEvent(
                text=normalized,
                stability=stability,
                start_ms=start_ms,
                end_ms=end_ms,
                attachments=_artifacts_to_payload(turn_input, include_inline_data=True),
                ts=final_ts,
            )
        )
        append_trace_log(
            "realtime.asr.final",
            {
                "text": normalized,
                "stability": stability,
                "start_ms": start_ms,
                "end_ms": end_ms,
                "attachments": _artifacts_to_payload(turn_input, include_inline_data=False),
                "asr_final_latency_ms": asr_final_latency_ms,
            },
            scope="realtime_asr",
        )
        return self.submit_turn(
            turn_input,
            user_text=normalized or turn_input.multimodal_summary(),
            asr_final_at=final_ts,
            asr_final_latency_ms=asr_final_latency_ms,
        )

    def submit_turn(
            self,
            turn_input: TurnInput,
            *,
            user_text: str | None = None,
            asr_final_at: float | None = None,
            asr_final_latency_ms: float | None = None,
    ) -> int | None:
        normalized = turn_input.normalized_text()
        if self._shutdown.is_set():
            return None
        if not normalized and not turn_input.artifacts:
            return None

        # Text / multimodal submit is also an explicit new user turn, so cut off
        # any in-flight response before turn setup and state writes.
        self._preempt_active_turn_for_user_input(
            reason="new_user_turn",
            detail=user_text or normalized or turn_input.multimodal_summary(),
        )

        ctrl = self.begin_turn(user_text=user_text or normalized or turn_input.multimodal_summary())
        ctrl.t0_submit_at = time.monotonic()
        self.state.upsert_realtime_user_turn(ctrl.turn_id, turn_input)
        append_trace_log(
            "realtime.turn.submitted",
            {
                "turn_input": sanitize_turn_input(turn_input),
                "user_text": user_text or normalized or turn_input.multimodal_summary(),
                "asr_final_at": asr_final_at,
                "asr_final_latency_ms": asr_final_latency_ms,
            },
            turn_id=ctrl.turn_id,
            scope="realtime_turn",
        )
        ctrl.asr_final_at = asr_final_at
        ctrl.asr_final_latency_ms = asr_final_latency_ms
        self._emit_metrics(ctrl)
        worker = threading.Thread(target=self._run_turn, args=(ctrl, turn_input), daemon=True)
        ctrl.worker_thread = worker
        worker.start()
        return ctrl.turn_id

    def interrupt(self, reason: str = "manual") -> None:
        with self._lock:
            ctrl = self._active

        if ctrl is None:
            return

        with self._lock:
            self._interrupt_count += 1
        ctrl.interrupt()
        self.events.drop_turn_events(ctrl.turn_id, {"assistant_token", "tts_chunk"})
        self.events.publish(ControlEvent(action="interrupt", detail=reason, turn_id=ctrl.turn_id))
        self._emit_state(TurnStatus.INTERRUPTING, turn_id=ctrl.turn_id, detail=reason)
        self._emit_metrics(ctrl)

        if bool(getattr(settings.runtime, "realtime_audio_rebuild_on_interrupt", False)):
            try:
                self.bridge.stop_current_stream()
                self.bridge.new_stream()
                self.events.publish(ControlEvent(action="new_stream", detail="bridge_rebuilt", turn_id=ctrl.turn_id))
            except Exception as exc:
                self.events.publish(ErrorEvent(scope="bridge", message=str(exc), turn_id=ctrl.turn_id))

        self._emit_state(TurnStatus.LISTENING, turn_id=ctrl.turn_id, detail="interrupted")

    def shutdown(self) -> None:
        self._shutdown.set()
        self.interrupt(reason="shutdown")
        self._emit_state(TurnStatus.SHUTDOWN, detail="session_shutdown")

    def poll_events(self, max_items: int = 64) -> list[dict[str, object]]:
        return [event.to_payload() for event in self.events.drain(max_items=max_items)]

    def _emit_state(self, status: TurnStatus, *, turn_id: int | None = None, detail: str = "") -> None:
        with self._lock:
            self._session_status = status
        self.events.publish(StateChangedEvent(state=status.value, detail=detail, turn_id=turn_id))

    def _emit_metrics(self, ctrl: TurnControl | None = None) -> None:
        with self._lock:
            active = ctrl or self._active
            interrupt_count = self._interrupt_count
        asr_final_latency_ms = active.asr_final_latency_ms if active is not None else None
        first_token_latency_ms = None
        first_audio_latency_ms = None
        if active is not None and active.asr_final_at is not None and active.first_token_at is not None:
            first_token_latency_ms = max(0.0, (active.first_token_at - active.asr_final_at) * 1000.0)
        if active is not None and active.asr_final_at is not None and active.first_audio_at is not None:
            first_audio_latency_ms = max(0.0, (active.first_audio_at - active.asr_final_at) * 1000.0)
        timeline_ms: dict[str, float | None] = {}
        if active is not None and active.t0_submit_at is not None:
            t0 = active.t0_submit_at

            def _delta(ts_value: float | None) -> float | None:
                if ts_value is None:
                    return None
                return max(0.0, (ts_value - t0) * 1000.0)

            timeline_ms = {
                "t0_submit": 0.0,
                "t1_prepare_state_done": _delta(active.t1_prepare_state_done_at),
                "t2_router_done": _delta(active.t2_router_done_at),
                "t3_turn_plan_done": _delta(active.t3_turn_plan_done_at),
                "t4_first_token": _delta(active.t4_first_token_at),
                "t5_first_tts_submit": _delta(active.t5_first_tts_submit_at),
                "t6_first_tts_chunk": _delta(active.t6_first_tts_chunk_at),
                "t7_first_push_pcm": _delta(active.t7_first_push_pcm_at),
            }
        self.events.publish(
            MetricsDebugEvent(
                asr_final_latency_ms=asr_final_latency_ms,
                first_token_latency_ms=first_token_latency_ms,
                first_audio_latency_ms=first_audio_latency_ms,
                interrupt_count=interrupt_count,
                timeline_ms=timeline_ms,
                turn_id=(active.turn_id if active is not None else None),
            )
        )

    def _create_tts_pipeline(self) -> StreamingVoicePipeline | None:
        if not settings.voice_config.api_key:
            return None
        try:
            return StreamingVoicePipeline(
                VoiceStreamConfig(
                    api_key=settings.voice_config.api_key,
                    model=settings.voice_config.model,
                    voice=settings.voice_config.voice,
                    volume=settings.voice_config.volume,
                    speech_rate=settings.voice_config.speech_rate,
                    pitch_rate=settings.voice_config.pitch_rate,
                    instruction=settings.voice_config.instruction,
                    audio_format="pcm",
                    sample_rate=settings.voice_config.sample_rate,
                )
            )
        except CosyVoiceSDKError as exc:
            self.events.publish(ErrorEvent(scope="tts", message=str(exc)))
            return None

    def _start_audio_pump(self, ctrl: TurnControl, tts_pipeline: StreamingVoicePipeline) -> threading.Thread:
        sample_rate = int(getattr(self.bridge.config, "sample_rate", settings.voice_config.sample_rate) or 24000)
        frame_ms = int(getattr(settings.runtime, "realtime_audio_frame_ms", 60) or 60)
        frame_ms = max(20, min(200, frame_ms))
        frame_bytes = int(sample_rate * (frame_ms / 1000.0) * 2)
        max_lead_seconds = float(getattr(settings.runtime, "realtime_audio_max_lead_seconds", 0.05) or 0.05)
        debug_dump = bool(getattr(settings.runtime, "debug_audio_dump", False))

        def _pump() -> None:
            _LOG.info("Realtime session audio pump started: turn=%s sr=%s frame_ms=%s", ctrl.turn_id, sample_rate,
                      frame_ms)
            pending = bytearray()
            pump_started_at = time.monotonic()
            total_bytes = 0
            push_seq = 0
            chunks_seen = 0
            nonempty_chunks = 0
            done_since: float | None = None
            last_chunk_time = time.monotonic()
            cleanup_start = 0.0
            debug_pcm = bytearray() if debug_dump else None
            exit_reason = "unknown"
            cleanup_elapsed_ms = 0.0

            def _push_aligned(data: bytes) -> int:
                if not data:
                    return 0
                if (len(data) % 2) != 0:
                    data = data[:-1]
                if not data:
                    return 0
                with self._lock:
                    self._last_tts_chunk_at = time.monotonic()
                if ctrl.first_audio_at is None:
                    ctrl.first_audio_at = time.monotonic()
                    self._emit_metrics(ctrl)
                if ctrl.t7_first_push_pcm_at is None:
                    ctrl.t7_first_push_pcm_at = time.monotonic()
                    append_trace_log(
                        "realtime.turn.t7_first_push_pcm",
                        {
                            "timeline_ms": max(0.0, (ctrl.t7_first_push_pcm_at - (ctrl.t0_submit_at or ctrl.started_at)) * 1000.0),
                            "bytes_len": len(data),
                        },
                        turn_id=ctrl.turn_id,
                        scope="realtime_audio",
                    )
                    self._emit_metrics(ctrl)
                self.bridge.push_pcm_bytes(data)
                if debug_pcm is not None:
                    debug_pcm.extend(data)
                self.events.publish(
                    TtsChunkEvent(
                        bytes_len=len(data),
                        turn_id=ctrl.turn_id,
                        sample_rate=sample_rate,
                        pcm_base64=base64.b64encode(data).decode("ascii"),
                    )
                )
                return len(data)

            def _flush_pending(full_frames_only: bool = True) -> None:
                nonlocal total_bytes, push_seq
                if not pending:
                    return
                if full_frames_only:
                    while len(pending) >= frame_bytes and not ctrl.stop_event.is_set():
                        chunk = bytes(pending[:frame_bytes])
                        del pending[:frame_bytes]
                        written = _push_aligned(chunk)
                        if written:
                            total_bytes += written
                            push_seq += 1
                else:
                    written = _push_aligned(bytes(pending))
                    if written:
                        total_bytes += written
                        push_seq += 1
                    pending.clear()

            def _pacer_sleep_if_ahead() -> None:
                pushed_seconds = (total_bytes / 2) / float(sample_rate)
                elapsed = time.monotonic() - pump_started_at
                lead = pushed_seconds - elapsed
                if lead > max_lead_seconds:
                    time.sleep(min(0.05, max(0.0, lead - max_lead_seconds)))

            while not ctrl.stop_event.is_set():
                try:
                    got_audio = False
                    chunks = tts_pipeline.pop_chunks()
                    chunks_seen += len(chunks)
                    for chunk in chunks:
                        if chunk:
                            nonempty_chunks += 1
                            pending.extend(chunk)
                            got_audio = True
                            last_chunk_time = time.monotonic()
                            if ctrl.t6_first_tts_chunk_at is None:
                                ctrl.t6_first_tts_chunk_at = last_chunk_time
                                append_trace_log(
                                    "realtime.turn.t6_first_tts_chunk",
                                    {
                                        "timeline_ms": max(0.0, (ctrl.t6_first_tts_chunk_at - (ctrl.t0_submit_at or ctrl.started_at)) * 1000.0),
                                        "chunk_bytes": len(chunk),
                                    },
                                    turn_id=ctrl.turn_id,
                                    scope="realtime_tts",
                                )
                                self._emit_metrics(ctrl)

                    if len(pending) >= frame_bytes:
                        _flush_pending(full_frames_only=True)
                        _pacer_sleep_if_ahead()

                    if tts_pipeline.error:
                        self.events.publish(
                            ErrorEvent(scope="tts", message=str(tts_pipeline.error), turn_id=ctrl.turn_id))
                        _LOG.error("Realtime session audio pump saw TTS error: turn=%s error=%s", ctrl.turn_id,
                                   tts_pipeline.error)
                        exit_reason = "tts_error"
                        break

                    if tts_pipeline.done:
                        if got_audio:
                            done_since = None
                        else:
                            done_since = done_since or time.monotonic()
                            if (time.monotonic() - done_since) >= 0.6:
                                for chunk in tts_pipeline.pop_chunks():
                                    if chunk:
                                        chunks_seen += 1
                                        nonempty_chunks += 1
                                        pending.extend(chunk)
                                        last_chunk_time = time.monotonic()
                                _flush_pending(full_frames_only=True)
                                _pacer_sleep_if_ahead()
                                exit_reason = "done_drain_threshold"
                                break
                    else:
                        done_since = None

                    if pending and (got_audio or tts_pipeline.done):
                        _flush_pending(full_frames_only=True)
                        _pacer_sleep_if_ahead()

                    time.sleep(0.002)
                except Exception as exc:
                    _LOG.exception("Realtime session audio pump loop failed: turn=%s", ctrl.turn_id)
                    self.events.publish(ErrorEvent(scope="audio_pump", message=str(exc), turn_id=ctrl.turn_id))
                    time.sleep(0.01)

            if ctrl.stop_event.is_set():
                exit_reason = "stop_event"
                pending.clear()
                try:
                    self.bridge.flush()
                except Exception:
                    ctrl.pump_metrics = {
                        "chunks_seen": chunks_seen,
                        "nonempty_chunks": nonempty_chunks,
                        "pushes": push_seq,
                        "bytes_pushed": total_bytes,
                        "pending_bytes": len(pending),
                        "exit_reason": "stop_event_flush_error",
                        "elapsed_ms": max(0.0, (time.monotonic() - pump_started_at) * 1000.0),
                        "cleanup_elapsed_ms": 0.0,
                    }
                    return
                ctrl.pump_metrics = {
                    "chunks_seen": chunks_seen,
                    "nonempty_chunks": nonempty_chunks,
                    "pushes": push_seq,
                    "bytes_pushed": total_bytes,
                    "pending_bytes": len(pending),
                    "exit_reason": exit_reason,
                    "elapsed_ms": max(0.0, (time.monotonic() - pump_started_at) * 1000.0),
                    "cleanup_elapsed_ms": 0.0,
                }
                return

            cleanup_start = time.monotonic()
            while (time.monotonic() - cleanup_start) < 3.0:
                has_more = False
                for chunk in tts_pipeline.pop_chunks():
                    if chunk:
                        chunks_seen += 1
                        nonempty_chunks += 1
                        pending.extend(chunk)
                        has_more = True
                        last_chunk_time = time.monotonic()
                _flush_pending(full_frames_only=True)
                _pacer_sleep_if_ahead()
                if not has_more and (time.monotonic() - last_chunk_time) >= 0.3:
                    exit_reason = "cleanup_drain_complete"
                    break
                time.sleep(0.03)

            _flush_pending(full_frames_only=False)
            _pacer_sleep_if_ahead()
            time.sleep(0.3)
            cleanup_elapsed_ms = max(0.0, (time.monotonic() - cleanup_start) * 1000.0)
            if exit_reason == "unknown":
                exit_reason = "cleanup_timeout"
            ctrl.pump_metrics = {
                "chunks_seen": chunks_seen,
                "nonempty_chunks": nonempty_chunks,
                "pushes": push_seq,
                "bytes_pushed": total_bytes,
                "pending_bytes": len(pending),
                "exit_reason": exit_reason,
                "elapsed_ms": max(0.0, (time.monotonic() - pump_started_at) * 1000.0),
                "cleanup_elapsed_ms": cleanup_elapsed_ms,
            }
            _LOG.info(
                "Realtime session audio pump finished: turn=%s pushes=%s bytes=%s chunks=%s nonempty_chunks=%s pending=%s exit_reason=%s cleanup_ms=%s",
                ctrl.turn_id,
                push_seq,
                total_bytes,
                chunks_seen,
                nonempty_chunks,
                len(pending),
                exit_reason,
                int(cleanup_elapsed_ms),
            )

        thread = threading.Thread(target=_pump, daemon=True)
        ctrl.pump_thread = thread
        thread.start()
        return thread

    @staticmethod
    def _normalized_match_text(text: str) -> str:
        """将文本统一化以用于回声比对。

        去除所有空白字符并转小写，使中英文文本在字符串匹配时不受
        标点、空格、大小写差异的干扰。
        """
        return "".join(str(text or "").lower().split())

    def _looks_like_playback_echo(self, text: str, active: TurnControl | None) -> bool:
        """判断 ASR partial 文本是否是 TTS 播放回声，而非用户真实输入。

        问题背景
        --------
        麦克风在 AVA 朗读时会拾取扬声器声音，ASR 将其识别为 partial
        结果推送上来。如果不过滤，这些"回声"会错误地触发 barge-in
        打断，导致 AVA 自己打断自己。

        检测策略（三道关卡，逐层过滤）
        --------------------------------
        1. **时间窗口**：只在 TTS 最后一帧推出后的 ``echo_detection_window_seconds``
           秒内启用检测。窗口之外的 ASR 输入一律视为真实用户输入，直接放行。

        2. **最小字符数**：ASR partial 过短（< ``echo_detection_min_chars``）时
           无法做有效比对，直接放行，避免误判短句。

        3. **文本相似度**：
           - 先做**精确子串匹配**：若 partial 完整出现在 assistant 文本尾部，
             则直接判定为回声（高置信度）。
           - 再做 **SequenceMatcher 模糊匹配**：针对 assistant 尾部截取
             与 partial 等比例长度的片段，若相似度 ≥
             ``echo_detection_similarity_threshold`` 则判定为回声。
             仅比对尾部而非全文，是因为 TTS 朗读时 ASR 拾取的永远是
             当前正在播放的部分（即文本末尾），全文匹配会引入大量噪声。

        配置项（均位于 config.yaml runtime 块）
        ----------------------------------------
        - ``echo_detection_window_seconds``     (默认 0.5s)
        - ``echo_detection_min_chars``          (默认 4 字符)
        - ``echo_detection_similarity_threshold`` (默认 0.85)

        返回
        ----
        bool：True 表示判定为回声，调用方应跳过 barge-in 处理；
              False 表示视为真实用户输入，正常继续。
        """
        # 前置守卫：没有正在进行的轮次或文本为空，无需检测
        if active is None:
            return False
        if not text or not active.assistant_text:
            return False

        now = time.monotonic()
        with self._lock:
            last_tts_chunk_at = self._last_tts_chunk_at

        # --- 关卡 1：时间窗口 ---
        # 超出窗口说明 TTS 已停止一段时间，此时 ASR 输入必然是真实用户输入
        echo_window = float(
            getattr(settings.runtime, "echo_detection_window_seconds", 0.5) or 0.5
        )
        if last_tts_chunk_at <= 0 or (now - last_tts_chunk_at) > echo_window:
            return False

        partial = self._normalized_match_text(text)

        # --- 关卡 2：最小字符数 ---
        # 文本过短无法可靠比对，放行避免误判（如用户说"嗯"、"好"）
        echo_min_chars = int(
            getattr(settings.runtime, "echo_detection_min_chars", 4) or 4
        )
        if len(partial) < echo_min_chars:
            return False

        assistant = self._normalized_match_text(active.assistant_text)
        if not assistant:
            return False

        # --- 关卡 3：文本相似度 ---
        # 只取 assistant 文本尾部做比对：TTS 当前播放的是末尾部分，
        # 取尾部 tail_window 个字符，窗口大小为 partial 长度的 6 倍
        # （给模糊匹配留足余量），但不超过 assistant 总长度。
        tail_window = max(48, min(len(assistant), len(partial) * 6))
        assistant_tail = assistant[-tail_window:]

        # 精确子串匹配：partial 完整包含在尾部，高置信度回声
        if partial in assistant_tail or assistant_tail.endswith(partial):
            return True

        # 模糊匹配：取与 partial 等比例长度的尾部片段做 SequenceMatcher 比对
        compare_tail = assistant_tail[-max(len(partial), min(len(assistant_tail), len(partial) * 2)):]
        ratio = SequenceMatcher(None, partial, compare_tail).ratio()
        echo_threshold = float(
            getattr(settings.runtime, "echo_detection_similarity_threshold", 0.85) or 0.85
        )
        return ratio >= echo_threshold

    def _run_turn(self, ctrl: TurnControl, turn_input: TurnInput) -> None:
        assistant_text = ""
        decision = None
        plan = None
        tts_pipeline: StreamingVoicePipeline | None = None
        pump_thread: threading.Thread | None = None
        turn_finalized = False
        token_count = 0
        token_chars = 0
        forced_pump_stop = False
        llm_stream_started_at: float | None = None
        llm_stream_finished_at: float | None = None
        speech_buffer: LatexAwareSpeechBuffer | None = None

        try:
            prepare_state_for_turn(self.state, turn_input)
            ctrl.t1_prepare_state_done_at = time.monotonic()
            append_trace_log(
                "realtime.turn.t1_prepare_state_done",
                {
                    "timeline_ms": max(0.0, (ctrl.t1_prepare_state_done_at - (ctrl.t0_submit_at or ctrl.started_at)) * 1000.0),
                },
                turn_id=ctrl.turn_id,
                scope="realtime_turn",
            )
            snapshot = assemble_context(
                self.state,
                turn_input,
                self.history_window,
                current_turn_id=ctrl.turn_id,
                max_context_messages=self.max_context_messages,
                profile="router",
            )
            append_trace_log(
                "realtime.context.assembled",
                _compact_snapshot_trace(snapshot),
                turn_id=ctrl.turn_id,
                scope="realtime_turn",
            )
            self.events.publish(
                ContextDebugEvent(
                    memory_summary=snapshot.recent_turns_summary,
                    history_summary=snapshot.recent_history_summary,
                    multimodal_summary=snapshot.multimodal_summary,
                    facts=snapshot.facts,
                    artifacts=_artifacts_to_payload(turn_input),
                    turn_id=ctrl.turn_id,
                )
            )
            decision, snapshot = self.router.route_with_context(
                turn_input,
                self.state,
                self.history_window,
                max_context_messages=self.max_context_messages,
                current_turn_id=ctrl.turn_id,
                snapshot=snapshot,
            )
            ctrl.t2_router_done_at = time.monotonic()
            append_trace_log(
                "realtime.turn.t2_router_done",
                {
                    "timeline_ms": max(0.0, (ctrl.t2_router_done_at - (ctrl.t0_submit_at or ctrl.started_at)) * 1000.0),
                    "decision": sanitize_value(decision.model_dump()),
                },
                turn_id=ctrl.turn_id,
                scope="realtime_turn",
            )
            if ctrl.stop_event.is_set():
                return

            plan = build_turn_plan(
                state=self.state,
                turn_input=turn_input,
                decision=decision,
                prompt_center=self.prompt_center,
                history_window=self.history_window,
                max_context_messages=self.max_context_messages,
                snapshot=snapshot,
                current_turn_id=ctrl.turn_id,
            )
            ctrl.t3_turn_plan_done_at = time.monotonic()
            append_trace_log(
                "realtime.turn.t3_turn_plan_done",
                {
                    "timeline_ms": max(0.0, (ctrl.t3_turn_plan_done_at - (ctrl.t0_submit_at or ctrl.started_at)) * 1000.0),
                    "strategy_id": plan.strategy.strategy_id,
                    "render_template": plan.strategy.render_template,
                },
                turn_id=ctrl.turn_id,
                scope="realtime_turn",
            )
            self.events.publish(
                RouteDecisionEvent(
                    session_scene=decision.session_scene,
                    turn_scene=decision.turn_scene,
                    confidence=decision.confidence,
                    handler=plan.orchestrator_name,
                    strategy_id=plan.strategy.strategy_id,
                    delivery_mode=plan.strategy.delivery_mode,
                    ui_mode=plan.strategy.ui_mode,
                    turn_id=ctrl.turn_id,
                )
            )
            evaluation_tags = build_evaluation_tags(self.state, turn_input, decision, plan.strategy)
            self.events.publish(
                StrategyDebugEvent(
                    branch=evaluation_tags.get("branch", decision.turn_scene),
                    strategy_id=plan.strategy.strategy_id,
                    strategy_name=plan.strategy.name,
                    strategy_source=plan.strategy.source,
                    render_template=plan.strategy.render_template,
                    delivery_mode=plan.strategy.delivery_mode,
                    ui_mode=plan.strategy.ui_mode,
                    user_followup_type=evaluation_tags.get("user_followup_type", ""),
                    artifact_subject_hint=str(plan.strategy.analysis.get("artifact_subject_hint", "") or ""),
                    artifact_task_hint=str(plan.strategy.analysis.get("artifact_task_hint", "") or ""),
                    artifact_text=str(((plan.strategy.analysis.get("signals", {}) or {}).get("artifact_text", "")) or ""),
                    turn_id=ctrl.turn_id,
                )
            )
            system_prompt = ""
            if plan.responder_messages:
                first = plan.responder_messages[0]
                if str(first.get("role", "")) == "system":
                    system_prompt = _compact_debug_prompt(_message_content_to_text(first.get("content", "")))
            self.events.publish(
                PromptDebugEvent(
                    handler=plan.orchestrator_name,
                    system_prompt=system_prompt,
                    strategy_id=plan.strategy.strategy_id,
                    render_template=plan.strategy.render_template,
                    delivery_mode=plan.strategy.delivery_mode,
                    ui_mode=plan.strategy.ui_mode,
                    turn_id=ctrl.turn_id,
                )
            )

            tts_pipeline = self._create_tts_pipeline()
            if tts_pipeline is not None:
                self.attach_tts(ctrl, tts_pipeline)
                pump_thread = self._start_audio_pump(ctrl, tts_pipeline)
                if (
                    should_apply_math_oralizer(plan.strategy)
                    and settings.speech_postprocess.math_stream_buffer_enabled
                ):
                    speech_buffer = LatexAwareSpeechBuffer(
                        strategy=plan.strategy,
                        flush_chars=max(16, int(settings.speech_postprocess.stream_flush_chars or 72)),
                    )

            llm_stream_started_at = time.monotonic()
            first_token = True

            def _submit_tts_text(text: str) -> None:
                if tts_pipeline is None or not text:
                    return
                if ctrl.t5_first_tts_submit_at is None:
                    ctrl.t5_first_tts_submit_at = time.monotonic()
                    append_trace_log(
                        "realtime.turn.t5_first_tts_submit",
                        {
                            "timeline_ms": max(0.0, (ctrl.t5_first_tts_submit_at - (ctrl.t0_submit_at or ctrl.started_at)) * 1000.0),
                            "token_preview": text[:80],
                        },
                        turn_id=ctrl.turn_id,
                        scope="realtime_tts",
                    )
                    self._emit_metrics(ctrl)
                tts_pipeline.submit(text)

            def _handle_token(token: str) -> None:
                nonlocal assistant_text, token_count, token_chars, first_token
                if ctrl.stop_event.is_set():
                    return
                assistant_text += token
                token_count += 1
                token_chars += len(token)
                ctrl.assistant_text = assistant_text
                if ctrl.first_token_at is None:
                    ctrl.first_token_at = time.monotonic()
                    ctrl.t4_first_token_at = ctrl.first_token_at
                    append_trace_log(
                        "realtime.turn.t4_first_token",
                        {
                            "timeline_ms": max(0.0, (ctrl.t4_first_token_at - (ctrl.t0_submit_at or ctrl.started_at)) * 1000.0),
                            "token_preview": token[:80],
                        },
                        turn_id=ctrl.turn_id,
                        scope="realtime_llm",
                    )
                    self._emit_metrics(ctrl)
                if first_token and tts_pipeline is None:
                    self._emit_state(TurnStatus.SPEAKING, turn_id=ctrl.turn_id, detail="text_streaming")
                first_token = False
                self.events.publish(AssistantTokenEvent(token=token, turn_id=ctrl.turn_id))
                if tts_pipeline is not None:
                    if speech_buffer is not None:
                        for chunk in speech_buffer.push(token):
                            _submit_tts_text(chunk)
                    else:
                        _submit_tts_text(token)
            reply_result = stream_reply_with_callbacks(
                state=self.state,
                turn_input=turn_input,
                decision=decision,
                plan=plan,
                snapshot=snapshot,
                api_base=settings.openai_config.api_base,
                api_key=settings.openai_config.api_key,
                model=settings.openai_config.multimodal_model or settings.openai_config.model,
                timeout=settings.openai_config.timeout,
                on_token=_handle_token,
                current_turn_id=ctrl.turn_id,
                stop_event=ctrl.stop_event,
            )
            assistant_text = reply_result.assistant_text
            ctrl.assistant_text = assistant_text
            llm_stream_finished_at = time.monotonic()
            _LOG.info(
                "Realtime turn llm stream finished: turn=%s backend=%s tokens=%s token_chars=%s assistant_chars=%s elapsed_ms=%s interrupted=%s",
                ctrl.turn_id,
                reply_result.backend,
                token_count,
                token_chars,
                len(assistant_text),
                int(max(0.0, ((llm_stream_finished_at or time.monotonic()) - (
                        llm_stream_started_at or ctrl.started_at)) * 1000.0)),
                bool(ctrl.stop_event.is_set() or ctrl.interrupted),
            )
            append_trace_log(
                "realtime.llm.stream.completed",
                {
                    "tokens": token_count,
                    "token_chars": token_chars,
                    "assistant_text": assistant_text,
                    "assistant_chars": len(assistant_text),
                    "llm_elapsed_ms": max(
                        0.0,
                        ((llm_stream_finished_at or time.monotonic()) - (llm_stream_started_at or ctrl.started_at))
                        * 1000.0,
                    ),
                    "backend": reply_result.backend,
                    "executor_debug": sanitize_value(reply_result.debug),
                    "interrupted": bool(ctrl.stop_event.is_set() or ctrl.interrupted),
                },
                turn_id=ctrl.turn_id,
                scope="realtime_llm",
            )

            if tts_pipeline is not None and speech_buffer is not None and not ctrl.stop_event.is_set():
                for chunk in speech_buffer.flush_final():
                    _submit_tts_text(chunk)

            if tts_pipeline is not None:
                tts_before_close = tts_pipeline.snapshot()
                close_started_at = time.monotonic()
                close_timeout_seconds = float(
                    getattr(settings.runtime, "realtime_tts_close_timeout_seconds", 45.0) or 45.0
                )
                if ctrl.stop_event.is_set():
                    tts_pipeline.interrupt()
                    closed = tts_pipeline.wait_done(2.0)
                else:
                    closed = tts_pipeline.close_with_timeout(close_timeout_seconds)
                    if not closed:
                        _LOG.warning(
                            "TTS feeder close timed out: turn=%s timeout_s=%s snapshot=%s",
                            ctrl.turn_id,
                            close_timeout_seconds,
                            tts_before_close,
                        )
                        tts_pipeline.interrupt()
                close_elapsed_ms = max(0.0, (time.monotonic() - close_started_at) * 1000.0)
                tts_after_close = tts_pipeline.snapshot()
                _LOG.info(
                    "Realtime turn TTS close summary: turn=%s closed=%s interrupted=%s close_ms=%s before=%s after=%s",
                    ctrl.turn_id,
                    closed,
                    bool(ctrl.stop_event.is_set() or ctrl.interrupted),
                    int(close_elapsed_ms),
                    tts_before_close,
                    tts_after_close,
                )
                append_trace_log(
                    "realtime.tts.close_summary",
                    {
                        "closed": closed,
                        "interrupted": bool(ctrl.stop_event.is_set() or ctrl.interrupted),
                        "close_ms": close_elapsed_ms,
                        "before": tts_before_close,
                        "after": tts_after_close,
                    },
                    turn_id=ctrl.turn_id,
                    scope="realtime_tts",
                )
                if pump_thread is not None:
                    pump_join_started_at = time.monotonic()
                    pump_timeout_seconds = (
                        2.0
                        if ctrl.stop_event.is_set()
                        else float(
                            getattr(settings.runtime, "realtime_audio_pump_drain_timeout_seconds", 45.0)
                            or 45.0
                        )
                    )
                    pump_thread.join(
                        timeout=pump_timeout_seconds
                    )
                    pump_wait_ms = max(0.0, (time.monotonic() - pump_join_started_at) * 1000.0)
                    if pump_thread.is_alive():
                        forced_pump_stop = True
                        _LOG.warning(
                            "Audio pump drain timed out: turn=%s timeout_s=%s wait_ms=%s metrics=%s forcing_stop=true",
                            ctrl.turn_id,
                            pump_timeout_seconds,
                            int(pump_wait_ms),
                            ctrl.pump_metrics or {},
                        )
                        ctrl.stop_event.set()
                        pump_thread.join(timeout=2.0)
                    _LOG.info(
                        "Realtime turn audio pump summary: turn=%s wait_ms=%s forced_stop=%s metrics=%s",
                        ctrl.turn_id,
                        int(pump_wait_ms),
                        forced_pump_stop,
                        ctrl.pump_metrics or {},
                    )
                    append_trace_log(
                        "realtime.audio_pump.summary",
                        {
                            "wait_ms": pump_wait_ms,
                            "forced_stop": forced_pump_stop,
                            "metrics": ctrl.pump_metrics or {},
                        },
                        turn_id=ctrl.turn_id,
                        scope="realtime_audio",
                    )

            interrupted = bool(ctrl.stop_event.is_set() or ctrl.interrupted)
            _LOG.info(
                "Realtime turn final summary: turn=%s interrupted=%s forced_pump_stop=%s tokens=%s token_chars=%s assistant_chars=%s llm_elapsed_ms=%s first_token_ms=%s first_audio_ms=%s pump_metrics=%s",
                ctrl.turn_id,
                interrupted,
                forced_pump_stop,
                token_count,
                token_chars,
                len(assistant_text),
                int(
                    max(
                        0.0,
                        ((llm_stream_finished_at or time.monotonic()) - (
                                llm_stream_started_at or ctrl.started_at)) * 1000.0,
                    )
                ),
                (
                    int(max(0.0, (ctrl.first_token_at - ctrl.asr_final_at) * 1000.0))
                    if ctrl.first_token_at is not None and ctrl.asr_final_at is not None
                    else -1
                ),
                (
                    int(max(0.0, (ctrl.first_audio_at - ctrl.asr_final_at) * 1000.0))
                    if ctrl.first_audio_at is not None and ctrl.asr_final_at is not None
                    else -1
                ),
                ctrl.pump_metrics or {},
            )
            append_trace_log(
                "realtime.turn.final_summary",
                {
                    "interrupted": interrupted,
                    "forced_pump_stop": forced_pump_stop,
                    "tokens": token_count,
                    "token_chars": token_chars,
                    "assistant_text": assistant_text,
                    "assistant_chars": len(assistant_text),
                    "llm_elapsed_ms": max(
                        0.0,
                        ((llm_stream_finished_at or time.monotonic()) - (llm_stream_started_at or ctrl.started_at))
                        * 1000.0,
                    ),
                    "first_token_ms": (
                        max(0.0, (ctrl.first_token_at - ctrl.asr_final_at) * 1000.0)
                        if ctrl.first_token_at is not None and ctrl.asr_final_at is not None
                        else None
                    ),
                    "first_audio_ms": (
                        max(0.0, (ctrl.first_audio_at - ctrl.asr_final_at) * 1000.0)
                        if ctrl.first_audio_at is not None and ctrl.asr_final_at is not None
                        else None
                    ),
                    "timeline_ms": {
                        "t0_submit": 0.0 if ctrl.t0_submit_at is not None else None,
                        "t1_prepare_state_done": (
                            max(0.0, (ctrl.t1_prepare_state_done_at - ctrl.t0_submit_at) * 1000.0)
                            if ctrl.t0_submit_at is not None and ctrl.t1_prepare_state_done_at is not None
                            else None
                        ),
                        "t2_router_done": (
                            max(0.0, (ctrl.t2_router_done_at - ctrl.t0_submit_at) * 1000.0)
                            if ctrl.t0_submit_at is not None and ctrl.t2_router_done_at is not None
                            else None
                        ),
                        "t3_turn_plan_done": (
                            max(0.0, (ctrl.t3_turn_plan_done_at - ctrl.t0_submit_at) * 1000.0)
                            if ctrl.t0_submit_at is not None and ctrl.t3_turn_plan_done_at is not None
                            else None
                        ),
                        "t4_first_token": (
                            max(0.0, (ctrl.t4_first_token_at - ctrl.t0_submit_at) * 1000.0)
                            if ctrl.t0_submit_at is not None and ctrl.t4_first_token_at is not None
                            else None
                        ),
                        "t5_first_tts_submit": (
                            max(0.0, (ctrl.t5_first_tts_submit_at - ctrl.t0_submit_at) * 1000.0)
                            if ctrl.t0_submit_at is not None and ctrl.t5_first_tts_submit_at is not None
                            else None
                        ),
                        "t6_first_tts_chunk": (
                            max(0.0, (ctrl.t6_first_tts_chunk_at - ctrl.t0_submit_at) * 1000.0)
                            if ctrl.t0_submit_at is not None and ctrl.t6_first_tts_chunk_at is not None
                            else None
                        ),
                        "t7_first_push_pcm": (
                            max(0.0, (ctrl.t7_first_push_pcm_at - ctrl.t0_submit_at) * 1000.0)
                            if ctrl.t0_submit_at is not None and ctrl.t7_first_push_pcm_at is not None
                            else None
                        ),
                    },
                    "pump_metrics": ctrl.pump_metrics or {},
                    "decision": sanitize_value(decision.model_dump() if decision is not None else {}),
                    "strategy": sanitize_value(plan.strategy.to_metadata() if plan is not None else {}),
                },
                turn_id=ctrl.turn_id,
                scope="realtime_turn",
            )
            if decision is not None:
                evaluation = build_evaluation_tags(self.state, turn_input, decision, plan.strategy)
                evaluation["turn_result"] = "interrupted" if interrupted else "completed"
                self.state.complete_realtime_turn(
                    ctrl.turn_id,
                    turn_input=turn_input,
                    assistant_text=assistant_text,
                    intent=decision.intent or decision.turn_scene,
                    decision=decision.model_dump(),
                    strategy=plan.strategy.to_metadata(),
                    evaluation=evaluation,
                    turn_status=("interrupted" if interrupted else "completed"),
                )
                turn_finalized = True
            self.events.publish(
                AssistantCompletedEvent(
                    text=assistant_text,
                    interrupted=interrupted,
                    turn_id=ctrl.turn_id,
                )
            )
        except Exception as exc:
            _LOG.exception("Realtime turn failed.")
            append_trace_log(
                "realtime.turn.error",
                {
                    "error": str(exc),
                    "assistant_text": assistant_text,
                    "decision": sanitize_value(decision.model_dump() if decision is not None else {}),
                    "strategy": sanitize_value(plan.strategy.to_metadata() if plan is not None else {}),
                },
                turn_id=ctrl.turn_id,
                scope="realtime_turn",
            )
            if decision is not None:
                evaluation = build_evaluation_tags(self.state, turn_input, decision, None)
                evaluation["turn_result"] = "error"
                self.state.complete_realtime_turn(
                    ctrl.turn_id,
                    turn_input=turn_input,
                    assistant_text=assistant_text,
                    intent=decision.intent or decision.turn_scene,
                    decision=decision.model_dump(),
                    strategy=None,
                    evaluation=evaluation,
                    turn_status="error",
                )
                turn_finalized = True
            self.events.publish(ErrorEvent(scope="turn", message=str(exc), turn_id=ctrl.turn_id))
        finally:
            if not turn_finalized:
                turn_status = "interrupted" if (ctrl.stop_event.is_set() or ctrl.interrupted) else "error"
                evaluation = None
                if decision is not None:
                    evaluation = build_evaluation_tags(self.state, turn_input, decision,
                                                       (plan.strategy if plan else None))
                    evaluation["turn_result"] = turn_status
                self.state.complete_realtime_turn(
                    ctrl.turn_id,
                    turn_input=turn_input,
                    assistant_text=assistant_text,
                    intent=(decision.intent or decision.turn_scene) if decision is not None else "",
                    decision=(decision.model_dump() if decision is not None else None),
                    strategy=(plan.strategy.to_metadata() if plan is not None else None),
                    evaluation=evaluation,
                    turn_status=turn_status,
                )
                append_trace_log(
                    "realtime.turn.persisted",
                    {
                        "turn_status": turn_status,
                        "assistant_text": assistant_text,
                        "decision": sanitize_value((decision.model_dump() if decision is not None else {})),
                        "strategy": sanitize_value((plan.strategy.to_metadata() if plan is not None else {})),
                        "evaluation": sanitize_value(evaluation or {}),
                    },
                    turn_id=ctrl.turn_id,
                    scope="realtime_turn",
                )
            if tts_pipeline is not None and tts_pipeline.error is not None:
                self.events.publish(ErrorEvent(scope="tts", message=str(tts_pipeline.error), turn_id=ctrl.turn_id))
            self.end_turn(ctrl)
