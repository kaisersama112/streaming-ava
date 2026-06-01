"""会话级全双工实时运行时。"""

from __future__ import annotations
import base64
from difflib import SequenceMatcher
import logging
import threading
import time
from typing import Any

# 上下文构建相关工具
from ava.multi_turn_context_builder import ContextCompiler, ConversationBuildOptions
# 评估标签构建
from ava.pipeline.output import build_evaluation_tags

# 推理运行时：执行已经准备好的轮次计划
from ava.inference_runtime import InferenceRuntime
from ava.router_selector import RouterService

# 数学语音缓冲与口语化处理
from ava.pipeline.speech import LatexAwareSpeechBuffer, should_apply_math_oralizer

# 用户打断检测
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
    PromptPackageDebugEvent,
    PromptDebugEvent,
    RealtimeEventBus,
    RouteDecisionEvent,
    StateChangedEvent,
    TtsChunkEvent,
)

# 轮次生命周期控制
from ava.pipeline.streaming.turn import TurnControl, TurnStatus

# 提示词管理中心
from ava.capabilities.prompt import build_prompt_center

# 流式语音播放管线
from ava.pipeline.streaming.voice_stream import StreamingVoicePipeline, VoiceStreamConfig

# 会话状态对象
from ava.domain.conversation.state import ConversationState

# 音频桥接层
from ava.interfaces.websocket import RealtimeAudioBridge

# TTS 异常类型
from ava.capabilities.tts import CosyVoiceSDKError, TTSError

# 全局配置
from configs import settings

# 日志实例
_LOG = logging.getLogger("streaming_ava.realtime.session")


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


def _message_content_to_text(content: Any) -> str:
    """
    将消息内容转换为纯文本。

    支持：
    - 字符串
    - OpenAI 多模态内容块列表
    """

    # 纯字符串直接返回
    if isinstance(content, str):
        return content

    # 多模态内容块
    if isinstance(content, list):
        parts: list[str] = []

        for block in content:
            if not isinstance(block, dict):
                continue

            # 文本块
            if block.get("type") in {"text", "input_text", "output_text"}:
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


def _assistant_message_text(assistant_message: dict[str, Any] | None) -> str:
    """提取标准助手消息中的文本内容。"""
    if not isinstance(assistant_message, dict):
        return ""
    parts: list[str] = []
    for block in list(assistant_message.get("content") or []):
        if not isinstance(block, dict):
            continue
        if str(block.get("type", "") or "").strip() != "output_text":
            continue
        text = str(block.get("text", "") or "").strip()
        if text:
            parts.append(text)
    return "\n".join(parts).strip()


class RealtimeConversationSession:
    """
    全双工实时语音会话运行时。

    主要职责：
    1. 管理实时轮次生命周期
    2. 管理 ASR / LLM / TTS 流
    3. 处理 barge-in（用户打断）
    4. 管理事件总线
    5. 维护会话状态
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
        - bridge: 音频桥接对象
        - state: 会话状态
        - history_window: 历史窗口大小
        - max_context_messages: 最大上下文消息数
        - session_id: 会话 ID
        """

        # 音频桥接对象
        self.bridge = bridge

        # 标准化会话 ID
        self.session_id = ConversationState.normalize_session_id(
            session_id or settings.runtime.default_session_id
        )

        # 加载会话状态
        if state is not None:
            self.state = state
        else:
            self.state = ConversationState(
                settings.runtime.state_file,
                settings.runtime.history_window,
                session_id=self.session_id,
            )
            self.state.load()

        self.session_id = self.state.session_id

        # 历史窗口
        self.history_window = history_window or settings.runtime.history_window

        # 上下文消息限制
        self.max_context_messages = settings.runtime.max_context_messages

        # 路由阶段最大上下文消息数
        self.router_max_context_messages = int(self.max_context_messages)

        # 回复阶段最大上下文消息数
        self.responder_max_context_messages = int(self.max_context_messages)

        # 提示词中心
        self.prompt_center = build_prompt_center()
        self.context_compiler = ContextCompiler()
        self.router_service = RouterService(
            prompt_center=self.prompt_center,
            context_compiler=self.context_compiler,
        )
        self.inference_runtime = InferenceRuntime(
            context_compiler=self.context_compiler,
        )

        # 实时事件总线
        self.events = RealtimeEventBus()

        # 线程锁
        self._lock = threading.RLock()

        # 当前激活轮次
        self._active: TurnControl | None = None

        # 轮次序号
        self._turn_seq = 0

        # 关闭标记
        self._shutdown = threading.Event()

        # 当前会话状态
        self._session_status = TurnStatus.LISTENING

        # 用户打断检测器
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

        # 最近一次 TTS 数据块时间
        self._last_tts_chunk_at: float = 0.0

        # 初始化状态
        self._emit_state(TurnStatus.LISTENING, detail="session_ready")

        # 输出初始指标事件
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
            user_message = dict(record.get("user_message") or {})
            assistant_message = dict(record.get("assistant_message") or {})

            turn_status = str(record.get("turn_status", "completed") or "completed")

            # 用户消息
            payload.append(
                {
                    "role": "user",
                    "key": f"{turn_key}-user",
                    "content": list(user_message.get("content") or []),
                    "created_at": record.get("created_at") or "",
                }
            )

            # 助手消息
            if list(assistant_message.get("content") or []) or strategy or evaluation or decision:
                prompt_package = dict(strategy.get("prompt_package") or {})
                prompt_profile = dict(evaluation or {})
                prompt_profile["capability"] = prompt_profile.get("capability") or prompt_package.get("capability", "")
                prompt_profile["task"] = prompt_profile.get("task") or prompt_package.get("task", "")
                prompt_profile["knowledge"] = prompt_profile.get("knowledge") or prompt_package.get("knowledge", "")
                prompt_profile["method"] = prompt_profile.get("method") or prompt_package.get("method", "")
                prompt_profile["audience"] = prompt_profile.get("audience") or prompt_package.get("audience", "")
                skills = prompt_profile.get("skills")
                if not isinstance(skills, list):
                    skills = list(prompt_package.get("skills") or [])
                payload.append(
                    {
                        "role": "assistant",
                        "key": f"{turn_key}-assistant",
                        "content": list(assistant_message.get("content") or []),
                        "created_at": record.get("created_at") or "",
                        "intent": record.get("intent") or "",
                        "meta": {
                            "session_scene": prompt_profile.get("session_scene") or decision.get("session_scene", ""),
                            "turn_scene": prompt_profile.get("turn_scene") or decision.get("turn_scene", ""),
                            "capability": prompt_profile.get("capability", ""),
                            "task": prompt_profile.get("task", ""),
                            "knowledge": prompt_profile.get("knowledge", ""),
                            "method": prompt_profile.get("method", ""),
                            "audience": prompt_profile.get("audience", ""),
                            "skills": skills,
                            "user_followup_type": evaluation.get("user_followup_type", ""),
                            "prompt_source": evaluation.get("prompt_source") or strategy.get("source", ""),
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

    def begin_turn(self, user_message: dict[str, Any] | None = None) -> TurnControl:
        # 如果上一轮仍在执行，先打断，再为当前输入创建新轮次。
        with self._lock:
            prev_active = self._active
        if prev_active is not None and not prev_active.stop_event.is_set():
            self.interrupt(reason="new_turn")
        with self._lock:
            self._turn_seq += 1
            normalized_user_message = dict(user_message or {})
            ctrl = TurnControl(
                turn_id=self._turn_seq,
                stop_event=threading.Event(),
                bridge=self.bridge,
                user_message=normalized_user_message,
                status=TurnStatus.THINKING,
            )
            self._active = ctrl
            self._emit_state(TurnStatus.THINKING, turn_id=ctrl.turn_id, detail="turn_started")
            self.events.publish(
                ControlEvent(
                    action="start_turn",
                    detail=_message_content_to_text(normalized_user_message.get("content") or [])[:80],
                    turn_id=ctrl.turn_id,
                )
            )
            return ctrl

    def _preempt_active_turn_for_user_input(self, *, reason: str, detail: str = "") -> None:
        active = self.active
        if active is None:
            return
        if active.stop_event.is_set():
            return
        if active.status not in (TurnStatus.SPEAKING, TurnStatus.THINKING):
            return
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
        """
        处理未最终确认的 ASR partial 文本，但不提交新轮次。

        参数:
        - text: 当前 partial 文本。
        - stability: ASR 稳定度。
        - start_ms: 识别片段起始毫秒。
        - end_ms: 识别片段结束毫秒。
        - ts: 事件时间戳。

        返回:
        - None
        """
        active = self.active
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
                user_message={
                    "role": "user",
                    "content": [{"type": "input_text", "text": text}] if str(text or "").strip() else [],
                },
                stability=stability,
                start_ms=start_ms,
                end_ms=end_ms,
                turn_id=(active.turn_id if active else None),
                ts=ts,
            )
        )
        # 当助手正在思考或播报时，partial 也可以触发打断。
        # 检测器只负责判定，真正的中断动作由 `interrupt` 完成。
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
            content_blocks: list[dict[str, Any]] | None = None,
            stability: float | None = None,
            start_ms: int | None = None,
            end_ms: int | None = None,
            ts: float | None = None,
            source: str = "realtime_web",
    ) -> int | None:
        """
        处理最终确认的 ASR 文本，并将其提交为新的实时轮次。

        参数:
        - text: 最终识别文本。
        - content_blocks: 当前输入附带的标准内容块（除文本外也可包含图片、音频、文件）。
        - stability: ASR 稳定度。
        - start_ms: 识别片段起始毫秒。
        - end_ms: 识别片段结束毫秒。
        - ts: 事件时间戳。
        - source: 输入来源标记。

        返回:
        - int | None: 新建轮次的 `turn_id`，若未提交则返回 `None`。
        """
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

        user_message_content: list[dict[str, Any]] = []
        if normalized:
            user_message_content.append({"type": "input_text", "text": normalized})
        for block in list(content_blocks or []):
            if isinstance(block, dict):
                user_message_content.append(dict(block))
        user_message = {"role": "user", "content": user_message_content}
        if not user_message_content:
            return None

        # 最终 ASR 是明确的新用户输入信号。
        # 在真正提交新轮次前，先抢占当前仍在运行的助手回复。
        self._preempt_active_turn_for_user_input(
            reason="barge_in_final",
            detail=normalized or _message_content_to_text(user_message_content),
        )

        asr_final_latency_ms: float | None = None
        with self._lock:
            if self._last_audio_frame_ts is not None:
                asr_final_latency_ms = max(0.0, (final_ts - self._last_audio_frame_ts) * 1000.0)

        self.events.publish(
            AsrFinalEvent(
                user_message=user_message,
                stability=stability,
                start_ms=start_ms,
                end_ms=end_ms,
                ts=final_ts,
            )
        )
        return self.submit_turn(
            user_message,
            source=source,
            asr_final_at=final_ts,
            asr_final_latency_ms=asr_final_latency_ms,
        )

    def submit_turn(
            self,
            user_message: dict[str, Any],
            *,
            source: str = "runtime",
            asr_final_at: float | None = None,
            asr_final_latency_ms: float | None = None,
    ) -> int | None:
        """
        创建 `TurnControl`，写入待处理用户输入，并启动后台推理线程。

        参数:
        - user_message: 标准化后的 user message。
        - source: 输入来源标记。
        - asr_final_at: ASR final 到达时间。
        - asr_final_latency_ms: 从最后音频帧到 ASR final 的延迟。

        返回:
        - int | None: 新建轮次的 `turn_id`，若未提交则返回 `None`。
        """
        has_non_text_blocks = any(
            isinstance(block, dict) and str(block.get("type", "") or "").strip() != "input_text"
            for block in list(user_message.get("content") or [])
        )
        has_text_blocks = any(
            isinstance(block, dict)
            and str(block.get("type", "") or "").strip() == "input_text"
            and str(block.get("text", "") or "").strip()
            for block in list(user_message.get("content") or [])
        )
        if self._shutdown.is_set():
            return None
        if not has_text_blocks and not has_non_text_blocks:
            return None

        # 文本或多模态输入都代表明确的新用户轮次。
        # 在轮次创建和状态写入前，先中断任何仍在飞行中的回复。
        self._preempt_active_turn_for_user_input(
            reason="new_user_turn",
            detail=_message_content_to_text(user_message.get("content") or []),
        )

        ctrl = self.begin_turn(user_message=user_message)
        ctrl.t0_submit_at = time.monotonic()
        # 先持久化用户侧输入，这样即使后续被打断或报错，
        # 当前轮也仍然有可恢复的输入记录。
        self.state.upsert_realtime_user_turn(ctrl.turn_id, user_message, source=source)
        ctrl.asr_final_at = asr_final_at
        ctrl.asr_final_latency_ms = asr_final_latency_ms
        self._emit_metrics(ctrl)
        worker = threading.Thread(target=self._run_turn, args=(ctrl, dict(user_message)), daemon=True)
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
        """
        创建当前轮使用的流式 TTS 管线。

        返回:
        - StreamingVoicePipeline | None: 创建成功则返回管线对象，否则返回 `None`。
        """
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
        """
        启动音频泵线程，把 TTS 输出持续推送为 WebSocket PCM 音频帧。

        参数:
        - ctrl: 当前轮次控制对象。
        - tts_pipeline: 当前轮的 TTS 管线。

        返回:
        - threading.Thread: 已启动的音频泵线程。
        """
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
        """
        归一化文本，便于做回声匹配。

        参数:
        - text: 原始文本。

        返回:
        - str: 去空白并转小写后的文本。
        """
        return "".join(str(text or "").lower().split())

    def _looks_like_playback_echo(self, text: str, active: TurnControl | None) -> bool:
        """
        判断 ASR partial 是否更像 TTS 播放回声，而不是用户真实输入。

        参数:
        - text: 当前 ASR partial 文本。
        - active: 当前激活的轮次控制对象。

        返回:
        - bool: `True` 表示判定为回声，`False` 表示更像真实输入。

        判定步骤：
        1. 仅在最近发生过 TTS 播放时进入检测窗口。
        2. 过短的 partial 直接跳过，避免误判。
        3. 对助手文本尾部做精确或模糊匹配。
        """
        # 没有活动轮次，或当前没有助手文本时，不需要检测。
        if active is None:
            return False
        active_assistant_output_text = _assistant_message_text(active.assistant_message)
        if not text or not active_assistant_output_text:
            return False

        now = time.monotonic()
        with self._lock:
            last_tts_chunk_at = self._last_tts_chunk_at

        # 只在最近一次 TTS 输出后的短时间窗口内做回声判断。
        echo_window = float(
            getattr(settings.runtime, "echo_detection_window_seconds", 0.5) or 0.5
        )
        if last_tts_chunk_at <= 0 or (now - last_tts_chunk_at) > echo_window:
            return False

        partial = self._normalized_match_text(text)

        # partial 太短时无法可靠匹配，直接放行。
        echo_min_chars = int(
            getattr(settings.runtime, "echo_detection_min_chars", 4) or 4
        )
        if len(partial) < echo_min_chars:
            return False

        assistant = self._normalized_match_text(active_assistant_output_text)
        if not assistant:
            return False

        # 仅比较助手文本尾部，因为回声通常来自最近播报的那一段。
        tail_window = max(48, min(len(assistant), len(partial) * 6))
        assistant_tail = assistant[-tail_window:]

        # 先做精确子串匹配。
        if partial in assistant_tail or assistant_tail.endswith(partial):
            return True

        # 再做尾部模糊匹配。
        compare_tail = assistant_tail[-max(len(partial), min(len(assistant_tail), len(partial) * 2)):]
        ratio = SequenceMatcher(None, partial, compare_tail).ratio()
        echo_threshold = float(
            getattr(settings.runtime, "echo_detection_similarity_threshold", 0.85) or 0.85
        )
        return ratio >= echo_threshold

    def _run_turn(self, ctrl: TurnControl, user_message: dict[str, Any]) -> None:
        """
        执行单轮实时推理，并在结束后完成落盘。

        参数:
        - ctrl: 当前轮次控制对象。
        - user_message: 当前轮的标准 user message。

        返回:
        - None

        流程:
        1. 通过路由模块完成当前轮路由与 `TurnPlan` 构建。
        2. 将 `TurnPlan` 交给推理运行时执行回复。
        3. 将模型流式输出分发到界面事件与 TTS。
        4. 关闭 TTS 与音频泵线程。
        5. 持久化 completed / interrupted / error 状态。
        """
        assistant_output_buffer = ""
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
            ctrl.t1_prepare_state_done_at = time.monotonic()
            # 先构建用于路由的紧凑上下文。
            # 回复阶段会在执行计划构建时使用更完整的上下文。
            context = self.context_compiler.build_conversation_context(
                state=self.state,
                user_message=user_message,
                options=ConversationBuildOptions(
                    history_window=self.history_window,
                    current_turn_id=ctrl.turn_id,
                    max_context_messages=self.router_max_context_messages,
                    profile="router",
                ),
            )
            self.events.publish(
                ContextDebugEvent(
                    user_message=user_message,
                    turn_id=ctrl.turn_id,
                )
            )
            prepared_turn = self.router_service.prepare_turn(
                prompt_center=self.prompt_center,
                state=self.state,
                user_message=user_message,
                history_window=self.history_window,
                max_context_messages=self.responder_max_context_messages,
                current_turn_id=ctrl.turn_id,
                router_model=settings.openai_config.router_model,
                responder_model=settings.openai_config.model,
                timeout=int(settings.openai_config.timeout),
                api_base=settings.openai_config.api_base,
                api_key=settings.openai_config.api_key,
            )
            route_result = prepared_turn.route_result
            plan = prepared_turn.turn_plan
            decision = route_result.decision
            context = route_result.context
            ctrl.t2_router_done_at = time.monotonic()
            if ctrl.stop_event.is_set():
                return

            ctrl.t3_turn_plan_done_at = time.monotonic()
            prompt_profile = plan.prompt_profile
            active_skills = plan.active_skill_names
            self.events.publish(
                RouteDecisionEvent(
                    session_scene=decision.session_scene,
                    turn_scene=decision.turn_scene,
                    confidence=decision.confidence,
                    handler=plan.orchestrator_name,
                    prompt_profile=prompt_profile,
                    active_skills=active_skills,
                    turn_id=ctrl.turn_id,
                )
            )
            evaluation_tags = build_evaluation_tags(self.state, user_message, decision, plan.strategy)
            self.events.publish(
                PromptPackageDebugEvent(
                    prompt_profile=prompt_profile,
                    active_skills=active_skills,
                    prompt_source=(plan.strategy.source if plan.strategy is not None else ""),
                    user_followup_type=evaluation_tags.get("user_followup_type", ""),
                    prompt_package=(
                        plan.prompt_package.to_metadata()
                        if plan.prompt_package is not None
                        else {}
                    ),
                    analysis={
                        **dict((plan.strategy.analysis if plan.strategy is not None else {}) or {}),
                    },
                    turn_id=ctrl.turn_id,
                )
            )
            system_prompt = ""
            if plan.instructions:
                system_prompt = _compact_debug_prompt(plan.instructions)
            self.events.publish(
                PromptDebugEvent(
                    handler=plan.orchestrator_name,
                    system_prompt=system_prompt,
                    prompt_profile=prompt_profile,
                    active_skills=active_skills,
                    turn_id=ctrl.turn_id,
                )
            )

            # TTS 是可选链路，初始化失败时文本流仍可继续工作。
            tts_pipeline = self._create_tts_pipeline()
            if tts_pipeline is not None:
                self.attach_tts(ctrl, tts_pipeline)
                pump_thread = self._start_audio_pump(ctrl, tts_pipeline)
                oralizer_enabled = should_apply_math_oralizer()
                if (
                        oralizer_enabled
                        and settings.speech_postprocess.math_stream_buffer_enabled
                ):
                    speech_buffer = LatexAwareSpeechBuffer(
                        flush_chars=max(16, int(settings.speech_postprocess.stream_flush_chars or 72)),
                    )

            llm_stream_started_at = time.monotonic()
            first_token = True

            def _submit_tts_text(text: str) -> None:
                """
                把已经适合朗读的文本提交到 TTS 管线。

                参数:
                - text: 待送入 TTS 的文本片段。

                返回:
                - None
                """
                if tts_pipeline is None or not text:
                    return
                if ctrl.t5_first_tts_submit_at is None:
                    ctrl.t5_first_tts_submit_at = time.monotonic()
                    self._emit_metrics(ctrl)
                tts_pipeline.submit(text)

            def _handle_token(token: str) -> None:
                """
                处理单个流式 token，并分发到界面事件、指标与 TTS。

                参数:
                - token: 模型返回的增量文本。

                返回:
                - None
                """
                nonlocal assistant_output_buffer, token_count, token_chars, first_token
                if ctrl.stop_event.is_set():
                    return
                assistant_output_buffer += token
                token_count += 1
                token_chars += len(token)
                ctrl.assistant_message = {
                    "role": "assistant",
                    "content": (
                        [{"type": "output_text", "text": assistant_output_buffer}]
                        if str(assistant_output_buffer or "").strip()
                        else []
                    ),
                }
                if ctrl.first_token_at is None:
                    ctrl.first_token_at = time.monotonic()
                    ctrl.t4_first_token_at = ctrl.first_token_at
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

            reply_result = self.inference_runtime.stream_reply(
                state=self.state,
                plan=plan,
                user_message=user_message,
                context=context,
                on_token=_handle_token,
                current_turn_id=ctrl.turn_id,
                model=settings.openai_config.model,
                metadata={
                    "api_base": settings.openai_config.api_base,
                    "api_key": settings.openai_config.api_key,
                    "timeout": settings.openai_config.timeout,
                },
                stop_event=ctrl.stop_event,
            )
            ctrl.assistant_message = dict(reply_result.assistant_message or {})
            assistant_output_buffer = _assistant_message_text(ctrl.assistant_message)
            llm_stream_finished_at = time.monotonic()
            _LOG.info(
                "Realtime turn llm stream finished: turn=%s backend=%s tokens=%s token_chars=%s assistant_chars=%s elapsed_ms=%s interrupted=%s",
                ctrl.turn_id,
                reply_result.backend,
                token_count,
                token_chars,
                len(assistant_output_buffer),
                int(max(0.0, ((llm_stream_finished_at or time.monotonic()) - (
                        llm_stream_started_at or ctrl.started_at)) * 1000.0)),
                bool(ctrl.stop_event.is_set() or ctrl.interrupted),
            )
            # LaTeX 感知缓冲区可能暂存公式尾部，关闭 TTS 前先做一次最终 flush。
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

            interrupted = bool(ctrl.stop_event.is_set() or ctrl.interrupted)
            _LOG.info(
                "Realtime turn final summary: turn=%s interrupted=%s forced_pump_stop=%s tokens=%s token_chars=%s assistant_chars=%s llm_elapsed_ms=%s first_token_ms=%s first_audio_ms=%s pump_metrics=%s",
                ctrl.turn_id,
                interrupted,
                forced_pump_stop,
                token_count,
                token_chars,
                len(_assistant_message_text(ctrl.assistant_message)),
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
            if decision is not None:
                evaluation = build_evaluation_tags(self.state, user_message, decision, plan.strategy)
                evaluation["turn_result"] = "interrupted" if interrupted else "completed"
                # 在这里落盘最安全：用户输入、路由结果、执行策略和最终输出都已齐备。
                self.state.complete_realtime_turn(
                    ctrl.turn_id,
                    user_message=user_message,
                    assistant_message=ctrl.assistant_message,
                    intent=decision.intent or decision.turn_scene,
                    decision=decision.model_dump(),
                    strategy=(plan.strategy.to_metadata() if plan.strategy is not None else None),
                    evaluation=evaluation,
                    turn_status=("interrupted" if interrupted else "completed"),
                    llm_response_state=reply_result.debug.get("response_metadata", {}),
                )
                turn_finalized = True
            self.events.publish(
                AssistantCompletedEvent(
                    assistant_message=ctrl.assistant_message,
                    interrupted=interrupted,
                    turn_id=ctrl.turn_id,
                )
            )
        except Exception as exc:
            _LOG.exception("Realtime turn failed.")
            if decision is not None:
                evaluation = build_evaluation_tags(self.state, user_message, decision, None)
                evaluation["turn_result"] = "error"
                self.state.complete_realtime_turn(
                    ctrl.turn_id,
                    user_message=user_message,
                    assistant_message=ctrl.assistant_message,
                    intent=decision.intent or decision.turn_scene,
                    decision=decision.model_dump(),
                    strategy=None,
                    evaluation=evaluation,
                    turn_status="error",
                    llm_response_state={},
                )
                turn_finalized = True
            self.events.publish(ErrorEvent(scope="turn", message=str(exc), turn_id=ctrl.turn_id))
        finally:
            if not turn_finalized:
                turn_status = "interrupted" if (ctrl.stop_event.is_set() or ctrl.interrupted) else "error"
                evaluation = None
                if decision is not None:
                    evaluation = build_evaluation_tags(self.state, user_message, decision,
                                                       (plan.strategy if plan else None))
                    evaluation["turn_result"] = turn_status
                self.state.complete_realtime_turn(
                    ctrl.turn_id,
                    user_message=user_message,
                    assistant_message=ctrl.assistant_message,
                    intent=(decision.intent or decision.turn_scene) if decision is not None else "",
                    decision=(decision.model_dump() if decision is not None else None),
                    strategy=(plan.strategy.to_metadata() if plan is not None and plan.strategy is not None else None),
                    evaluation=evaluation,
                    turn_status=turn_status,
                    llm_response_state=(
                        reply_result.debug.get("response_metadata", {}) if 'reply_result' in locals() else {}),
                )
            if tts_pipeline is not None and tts_pipeline.error is not None:
                error_text = str(tts_pipeline.error)
                if "wait for complete timeout" not in error_text.lower():
                    self.events.publish(ErrorEvent(scope="tts", message=error_text, turn_id=ctrl.turn_id))
            self.end_turn(ctrl)
