"""Session-scoped full-duplex runtime."""

from __future__ import annotations
import base64
from difflib import SequenceMatcher
import logging
import threading
import time
from typing import Any

# 上下文构建相关工具
from ava.core.context import (
    AttachmentPayload,
    build_context_snapshot,
    build_turn_input,
)

# 会话状态加载与预处理
from ava.core.session import load_state, prepare_state_for_turn

# 评估标签构建
from ava.pipeline.output import build_evaluation_tags

# 生成阶段：构建 turn plan
from ava.pipeline.generation import build_turn_plan
from ava.pipeline.generation import stream_reply_with_callbacks

# 路由决策
from ava.pipeline.routing import route_with_context

# 数学语音缓冲与口语化处理
from ava.pipeline.speech import LatexAwareSpeechBuffer, should_apply_math_oralizer

# 打断（barge-in）检测
from ava.pipeline.streaming.barge_in import BargeInConfig, BargeInDetector

# 实时事件定义
from ava.core.events.realtime import (
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

# Turn 生命周期控制
from ava.pipeline.streaming.turn import TurnControl, TurnStatus

# Prompt 管理中心
from ava.capabilities.prompt import build_prompt_center

# Trace 日志工具
from ava.core.tracing import append_trace_log, sanitize_turn_input, sanitize_value

# 流式语音播放 Pipeline
from ava.pipeline.streaming.voice_stream import StreamingVoicePipeline, VoiceStreamConfig

# 多模态领域对象
from ava.domain.multimodal import MediaArtifact, TurnInput

# 会话状态对象
from ava.domain.conversation.state import ConversationState

# WebSocket 音频桥
from ava.interfaces.websocket import RealtimeAudioBridge

# TTS SDK 异常
from ava.capabilities.tts import CosyVoiceSDKError, TTSError

# 全局配置
from configs import settings

# 日志实例
_LOG = logging.getLogger("streaming_ava.realtime.session")


def _compact_snapshot_trace(snapshot: Any) -> dict[str, Any]:
    """
    将 context snapshot 压缩为适合 trace 日志输出的轻量结构。

    目的：
    - 避免 trace 日志过大
    - 保留关键上下文信息用于排查问题
    """
    return {
        "session_id": getattr(snapshot, "session_id", ""),
        "context_profile": getattr(snapshot, "context_profile", ""),
        "user_text": getattr(snapshot, "user_text", ""),
        "session_scene": getattr(snapshot, "session_scene", ""),
        "turn_scene": getattr(snapshot, "turn_scene", ""),

        # 只记录数量，不记录完整内容
        "history_messages_count": len(getattr(snapshot, "history_messages", []) or []),
        "artifacts_count": len(getattr(snapshot, "artifacts", ()) or ()),
        "reference_artifacts_count": len(getattr(snapshot, "reference_artifacts", ()) or ()),
    }


def _compact_debug_prompt(text: str, limit: int = 1200) -> str:
    """
    压缩 prompt 内容，避免调试日志过长。

    参数:
    - text: 原始 prompt
    - limit: 最大保留长度
    """
    value = str(text or "").strip()

    # 不超过限制直接返回
    if len(value) <= limit:
        return value

    # 超长则截断
    return f"{value[:limit].rstrip()}..."


def _artifact_to_payload(artifact: MediaArtifact, *, include_inline_data: bool = False) -> dict[str, Any]:
    """
    将 MediaArtifact 转换为可序列化 payload。

    include_inline_data:
        是否内联携带 base64 数据（图片/音频/视频）
    """

    # 基础 prompt dict
    payload = artifact.to_prompt_dict()

    # URI 信息
    if artifact.uri:
        payload["uri"] = artifact.uri

    # 可选内联数据
    if include_inline_data and artifact.data_url and artifact.kind in {"image", "audio", "video"}:
        payload["data_url"] = artifact.data_url

    return payload


def _artifacts_to_payload(turn_input: TurnInput, *, include_inline_data: bool = False) -> list[dict[str, Any]]:
    """
    将 TurnInput 中所有 artifact 转换为 payload 列表。
    """
    return [
        _artifact_to_payload(artifact, include_inline_data=include_inline_data)
        for artifact in turn_input.artifacts
    ]


def _message_content_to_text(content: Any) -> str:
    """
    将 message content 转换为纯文本。

    支持：
    - str
    - OpenAI multimodal block list
    """

    # 纯字符串直接返回
    if isinstance(content, str):
        return content

    # multimodal block
    if isinstance(content, list):
        parts: list[str] = []

        for block in content:
            if not isinstance(block, dict):
                continue

            # 文本 block
            if block.get("type") == "text":
                text = str(block.get("text", "")).strip()
                if text:
                    parts.append(text)
                    continue

            # 图片 / 音频 / 视频占位
            for key in ("image_url", "input_audio", "video"):
                if key in block:
                    parts.append(f"[{key}]")
                    break

        return "\n".join(parts).strip()

    return str(content or "")


class RealtimeConversationSession:
    """
    全双工实时语音会话 Runtime。

    主要职责：
    1. 管理实时 turn 生命周期
    2. 管理 ASR / LLM / TTS 流
    3. 处理 barge-in（用户打断）
    4. 管理事件总线
    5. 维护 conversation state
    """

    def __init__(
            self,
            bridge: RealtimeAudioBridge,
            *,
            state: ConversationState | None = None,
            history_window: int | None = None,
            max_context_messages: int | None = None,
            session_id: str | None = None,
    ) -> None:
        """
        初始化实时会话。

        参数:
        - bridge: WebSocket 音频桥
        - state: 会话状态
        - history_window: 历史窗口大小
        - max_context_messages: 最大上下文消息数
        - session_id: 会话 ID
        """

        # WebSocket 音频桥
        self.bridge = bridge

        # 标准化 session id
        self.session_id = ConversationState.normalize_session_id(
            session_id or settings.runtime.default_session_id
        )

        # 加载会话状态
        self.state = state or load_state(
            settings.runtime.state_file,
            settings.runtime.history_window,
            session_id=self.session_id,
        )

        self.session_id = self.state.session_id

        # 历史窗口
        self.history_window = history_window or settings.runtime.history_window

        # 上下文消息限制
        self.max_context_messages = (
                max_context_messages or settings.runtime.max_context_messages
        )

        # Router 阶段最大上下文
        self.router_max_context_messages = int(
            getattr(settings.runtime, "router_max_context_messages", 0)
            or self.max_context_messages
        )

        # Responder 阶段最大上下文
        self.responder_max_context_messages = int(
            getattr(settings.runtime, "responder_max_context_messages", 0)
            or self.max_context_messages
        )

        # Prompt 中心
        self.prompt_center = build_prompt_center()

        # 实时事件总线
        self.events = RealtimeEventBus()

        # 线程锁
        self._lock = threading.RLock()

        # 当前 active turn
        self._active: TurnControl | None = None

        # turn 序号
        self._turn_seq = 0

        # shutdown 标记
        self._shutdown = threading.Event()

        # 当前 session 状态
        self._session_status = TurnStatus.LISTENING

        # barge-in 检测器
        self._barge_in = BargeInDetector(
            BargeInConfig(
                min_partial_chars=int(
                    getattr(settings.runtime, "barge_in_partial_chars", 2) or 2
                ),
                stability_threshold=float(
                    getattr(settings.runtime, "barge_in_stability_threshold", 0.35)
                    or 0.35
                ),
                cooldown_ms=int(
                    getattr(settings.runtime, "barge_in_cooldown_ms", 450)
                    or 450
                ),
            )
        )

        # 打断计数
        self._interrupt_count = 0

        # 最近音频帧时间戳
        self._last_audio_frame_ts: float | None = None

        # 最近 TTS chunk 时间
        self._last_tts_chunk_at: float = 0.0

        # 初始化状态
        self._emit_state(TurnStatus.LISTENING, detail="session_ready")

        # 输出 metrics
        self._emit_metrics()

    # =====================================================================
    # 历史快照
    # =====================================================================

    def history_snapshot(self, limit: int = 12) -> list[dict[str, object]]:
        """
        返回历史对话快照。

        用于：
        - UI 历史展示
        - Debug
        - 恢复上下文
        """

        turns = self.state.turn_records[-max(0, limit):]

        payload: list[dict[str, object]] = []

        for index, record in enumerate(turns):
            turn_key = record.get("created_at") or f"history-{index}"

            decision = dict(record.get("decision") or {})
            strategy = dict(record.get("strategy") or {})
            evaluation = dict(record.get("evaluation") or {})

            turn_status = str(record.get("turn_status", "completed") or "completed")

            # 用户消息
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

            # assistant 文本
            assistant_text = str(record.get("assistant_text") or "").strip()

            # 补充状态文本
            if not assistant_text and turn_status == "interrupted":
                assistant_text = "已中断"
            elif not assistant_text and turn_status == "error":
                assistant_text = "本轮未完成"
            elif not assistant_text and turn_status == "pending":
                assistant_text = "处理中"

            # assistant 消息
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
        # 濡傛灉鏈夋鍦ㄨ繘琛岀殑杞锛屽厛璧板畬鏁存墦鏂祦绋嬶紙鍚?event drop + bridge rebuild锛?
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
        # 鍏佽鍦?SPEAKING 鎴?THINKING 闃舵瑙﹀彂 barge-in 鎵撴柇
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
        try:
            return StreamingVoicePipeline(
                VoiceStreamConfig(
                    voice=settings.voice_config,
                    audio_format="pcm",
                    sample_rate=settings.voice_config.sample_rate,
                    synth_complete_timeout_millis=int(
                        getattr(settings.runtime, "realtime_tts_complete_timeout_millis", 45000) or 45000
                    ),
                )
            )
        except (CosyVoiceSDKError, TTSError) as exc:
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
            done_drain_grace_seconds = float(
                getattr(settings.runtime, "realtime_tts_done_drain_grace_seconds", 2.0) or 2.0
            )
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
                            "timeline_ms": max(0.0, (
                                    ctrl.t7_first_push_pcm_at - (ctrl.t0_submit_at or ctrl.started_at)) * 1000.0),
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
                                        "timeline_ms": max(0.0, (ctrl.t6_first_tts_chunk_at - (
                                                ctrl.t0_submit_at or ctrl.started_at)) * 1000.0),
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
                        error_text = str(tts_pipeline.error)
                        snapshot = tts_pipeline.snapshot()
                        if "wait for complete timeout" in error_text.lower():
                            _LOG.warning(
                                "Realtime session audio pump saw soft TTS completion timeout: turn=%s error=%s snapshot=%s",
                                ctrl.turn_id,
                                tts_pipeline.error,
                                snapshot,
                            )
                            append_trace_log(
                                "realtime.tts.soft_timeout",
                                {
                                    "error": error_text,
                                    "snapshot": snapshot,
                                },
                                turn_id=ctrl.turn_id,
                                scope="realtime_tts",
                            )
                        else:
                            self.events.publish(
                                ErrorEvent(scope="tts", message=error_text, turn_id=ctrl.turn_id))
                            _LOG.error(
                                "Realtime session audio pump saw TTS error: turn=%s error=%s",
                                ctrl.turn_id,
                                tts_pipeline.error,
                            )
                        exit_reason = "tts_error"
                        break

                    if tts_pipeline.done:
                        if got_audio:
                            done_since = None
                        else:
                            done_since = done_since or time.monotonic()
                            idle_after_done = time.monotonic() - done_since
                            idle_since_chunk = time.monotonic() - last_chunk_time
                            if idle_after_done >= done_drain_grace_seconds and idle_since_chunk >= 0.4:
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
        """灏嗘枃鏈粺涓€鍖栦互鐢ㄤ簬鍥炲０姣斿銆?

        鍘婚櫎鎵€鏈夌┖鐧藉瓧绗﹀苟杞皬鍐欙紝浣夸腑鑻辨枃鏂囨湰鍦ㄥ瓧绗︿覆鍖归厤鏃朵笉鍙?
        鏍囩偣銆佺┖鏍笺€佸ぇ灏忓啓宸紓鐨勫共鎵般€?
        """
        return "".join(str(text or "").lower().split())

    def _looks_like_playback_echo(self, text: str, active: TurnControl | None) -> bool:
        """鍒ゆ柇 ASR partial 鏂囨湰鏄惁鏄?TTS 鎾斁鍥炲０锛岃€岄潪鐢ㄦ埛鐪熷疄杈撳叆銆?

        闂鑳屾櫙
        --------
        楹﹀厠椋庡湪 AVA 鏈楄鏃朵細鎷惧彇鎵０鍣ㄥ０闊筹紝ASR 灏嗗叾璇嗗埆涓?partial
        缁撴灉鎺ㄩ€佷笂鏉ャ€傚鏋滀笉杩囨护锛岃繖浜?鍥炲０"浼氶敊璇湴瑙﹀彂 barge-in
        鎵撴柇锛屽鑷?AVA 鑷繁鎵撴柇鑷繁銆?

        妫€娴嬬瓥鐣ワ紙涓夐亾鍏冲崱锛岄€愬眰杩囨护锛?
        --------------------------------
        1. **鏃堕棿绐楀彛**锛氬彧鍦?TTS 鏈€鍚庝竴甯ф帹鍑哄悗鐨?``echo_detection_window_seconds``
           绉掑唴鍚敤妫€娴嬨€傜獥鍙ｄ箣澶栫殑 ASR 杈撳叆涓€寰嬭涓虹湡瀹炵敤鎴疯緭鍏ワ紝鐩存帴鏀捐銆?

        2. **鏈€灏忓瓧绗︽暟**锛欰SR partial 杩囩煭锛? ``echo_detection_min_chars``锛夋椂
           鏃犳硶鍋氭湁鏁堟瘮瀵癸紝鐩存帴鏀捐锛岄伩鍏嶈鍒ょ煭鍙ャ€?

        3. **鏂囨湰鐩镐技搴?*锛?
           - 鍏堝仛**绮剧‘瀛愪覆鍖归厤**锛氳嫢 partial 瀹屾暣鍑虹幇鍦?assistant 鏂囨湰灏鹃儴锛?
             鍒欑洿鎺ュ垽瀹氫负鍥炲０锛堥珮缃俊搴︼級銆?
           - 鍐嶅仛 **SequenceMatcher 妯＄硦鍖归厤**锛氶拡瀵?assistant 灏鹃儴鎴彇
             涓?partial 绛夋瘮渚嬮暱搴︾殑鐗囨锛岃嫢鐩镐技搴?鈮?
             ``echo_detection_similarity_threshold`` 鍒欏垽瀹氫负鍥炲０銆?
             浠呮瘮瀵瑰熬閮ㄨ€岄潪鍏ㄦ枃锛屾槸鍥犱负 TTS 鏈楄鏃?ASR 鎷惧彇鐨勬案杩滄槸
             褰撳墠姝ｅ湪鎾斁鐨勯儴鍒嗭紙鍗虫枃鏈湯灏撅級锛屽叏鏂囧尮閰嶄細寮曞叆澶ч噺鍣０銆?

        閰嶇疆椤癸紙鍧囦綅浜?config.yaml runtime 鍧楋級
        ----------------------------------------
        - ``echo_detection_window_seconds``     (榛樿 0.5s)
        - ``echo_detection_min_chars``          (榛樿 4 瀛楃)
        - ``echo_detection_similarity_threshold`` (榛樿 0.85)

        杩斿洖
        ----
        bool锛歍rue 琛ㄧず鍒ゅ畾涓哄洖澹帮紝璋冪敤鏂瑰簲璺宠繃 barge-in 澶勭悊锛?
              False 琛ㄧず瑙嗕负鐪熷疄鐢ㄦ埛杈撳叆锛屾甯哥户缁€?
        """
        # 鍓嶇疆瀹堝崼锛氭病鏈夋鍦ㄨ繘琛岀殑杞鎴栨枃鏈负绌猴紝鏃犻渶妫€娴?
        if active is None:
            return False
        if not text or not active.assistant_text:
            return False

        now = time.monotonic()
        with self._lock:
            last_tts_chunk_at = self._last_tts_chunk_at

        # --- 鍏冲崱 1锛氭椂闂寸獥鍙?---
        # 瓒呭嚭绐楀彛璇存槑 TTS 宸插仠姝竴娈垫椂闂达紝姝ゆ椂 ASR 杈撳叆蹇呯劧鏄湡瀹炵敤鎴疯緭鍏?
        echo_window = float(
            getattr(settings.runtime, "echo_detection_window_seconds", 0.5) or 0.5
        )
        if last_tts_chunk_at <= 0 or (now - last_tts_chunk_at) > echo_window:
            return False

        partial = self._normalized_match_text(text)

        # --- 鍏冲崱 2锛氭渶灏忓瓧绗︽暟 ---
        # 鏂囨湰杩囩煭鏃犳硶鍙潬姣斿锛屾斁琛岄伩鍏嶈鍒わ紙濡傜敤鎴疯"鍡?銆?濂?锛?
        echo_min_chars = int(
            getattr(settings.runtime, "echo_detection_min_chars", 4) or 4
        )
        if len(partial) < echo_min_chars:
            return False

        assistant = self._normalized_match_text(active.assistant_text)
        if not assistant:
            return False

        # --- 鍏冲崱 3锛氭枃鏈浉浼煎害 ---
        # 鍙彇 assistant 鏂囨湰灏鹃儴鍋氭瘮瀵癸細TTS 褰撳墠鎾斁鐨勬槸鏈熬閮ㄥ垎锛?
        # 鍙栧熬閮?tail_window 涓瓧绗︼紝绐楀彛澶у皬涓?partial 闀垮害鐨?6 鍊?
        # 锛堢粰妯＄硦鍖归厤鐣欒冻浣欓噺锛夛紝浣嗕笉瓒呰繃 assistant 鎬婚暱搴︺€?
        tail_window = max(48, min(len(assistant), len(partial) * 6))
        assistant_tail = assistant[-tail_window:]

        # 绮剧‘瀛愪覆鍖归厤锛歱artial 瀹屾暣鍖呭惈鍦ㄥ熬閮紝楂樼疆淇″害鍥炲０
        if partial in assistant_tail or assistant_tail.endswith(partial):
            return True

        # 妯＄硦鍖归厤锛氬彇涓?partial 绛夋瘮渚嬮暱搴︾殑灏鹃儴鐗囨鍋?SequenceMatcher 姣斿
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
        oralizer_enabled = False

        try:
            prepare_state_for_turn(self.state, turn_input)
            ctrl.t1_prepare_state_done_at = time.monotonic()
            append_trace_log(
                "realtime.turn.t1_prepare_state_done",
                {
                    "timeline_ms": max(0.0, (
                            ctrl.t1_prepare_state_done_at - (ctrl.t0_submit_at or ctrl.started_at)) * 1000.0),
                },
                turn_id=ctrl.turn_id,
                scope="realtime_turn",
            )
            snapshot = build_context_snapshot(
                self.state,
                turn_input,
                self.history_window,
                current_turn_id=ctrl.turn_id,
                max_context_messages=self.router_max_context_messages,
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
                    multimodal_summary=turn_input.multimodal_summary() or snapshot.user_text,
                    artifacts=_artifacts_to_payload(turn_input),
                    turn_id=ctrl.turn_id,
                )
            )
            decision, snapshot = route_with_context(
                prompt_center=self.prompt_center,
                turn_input=turn_input,
                state=self.state,
                history_window=self.history_window,
                max_context_messages=self.router_max_context_messages,
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
                max_context_messages=self.responder_max_context_messages,
                snapshot=snapshot,
                current_turn_id=ctrl.turn_id,
            )
            ctrl.t3_turn_plan_done_at = time.monotonic()
            append_trace_log(
                "realtime.turn.t3_turn_plan_done",
                {
                    "timeline_ms": max(0.0,
                                       (ctrl.t3_turn_plan_done_at - (ctrl.t0_submit_at or ctrl.started_at)) * 1000.0),
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
                    artifact_text=str(
                        ((plan.strategy.analysis.get("signals", {}) or {}).get("artifact_text", "")) or ""),
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
                oralizer_enabled = should_apply_math_oralizer(plan.strategy)
                append_trace_log(
                    "realtime.tts.oralizer.config",
                    {
                        "branch": plan.strategy.branch,
                        "subject": plan.strategy.subject,
                        "oralizer_enabled": oralizer_enabled,
                        "math_stream_buffer_enabled": bool(settings.speech_postprocess.math_stream_buffer_enabled),
                    },
                    turn_id=ctrl.turn_id,
                    scope="realtime_tts",
                )
                if (
                        oralizer_enabled
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
                            "timeline_ms": max(0.0, (
                                    ctrl.t5_first_tts_submit_at - (ctrl.t0_submit_at or ctrl.started_at)) * 1000.0),
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
                            "timeline_ms": max(0.0, (
                                    ctrl.t4_first_token_at - (ctrl.t0_submit_at or ctrl.started_at)) * 1000.0),
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
                    "branch": (plan.strategy.branch if plan is not None else ""),
                    "subject": (plan.strategy.subject if plan is not None else ""),
                    "oralizer_enabled": oralizer_enabled,
                    "speech_buffer": (speech_buffer.snapshot() if speech_buffer is not None else None),
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
                    "branch": (plan.strategy.branch if plan is not None else ""),
                    "subject": (plan.strategy.subject if plan is not None else ""),
                    "oralizer_enabled": oralizer_enabled,
                    "speech_buffer": (speech_buffer.snapshot() if speech_buffer is not None else None),
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
                error_text = str(tts_pipeline.error)
                if "wait for complete timeout" not in error_text.lower():
                    self.events.publish(ErrorEvent(scope="tts", message=error_text, turn_id=ctrl.turn_id))
            self.end_turn(ctrl)
