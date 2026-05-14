"""DashScope Qwen-ASR-Realtime SDK adapter."""

from __future__ import annotations

import base64
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional


class ASRError(RuntimeError):
    """ASR operation error."""
    pass


@dataclass(frozen=True)
class ASRConfig:
    """ASR configuration."""
    api_key: str = ""
    provider: str = "qwen3_asr"
    model: str = "qwen3-asr-flash-realtime"
    language: str = "zh"
    sample_rate: int = 16000
    input_audio_format: str = "pcm"
    websocket_url: str = "wss://dashscope.aliyuncs.com/api-ws/v1/realtime"
    websocket_connect_timeout_sec: float = 10.0
    websocket_ping_interval_sec: float = 15.0
    websocket_ping_timeout_sec: float = 8.0
    enable_turn_detection: bool = True
    turn_detection_threshold: float = 0.0
    turn_detection_silence_duration_ms: int = 400
    doubao_x_api_key: str = ""
    doubao_resource_id: str = "volc.seedasr.sauc.duration"
    doubao_request_id: str = ""
    doubao_ws_url: str = "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async"
    doubao_uid: str = "streaming_ava"
    doubao_audio: dict[str, Any] | None = None
    doubao_request: dict[str, Any] | None = None


class StreamingQwenASR:
    """Thin wrapper around DashScope Qwen-ASR-Realtime with normalized errors."""

    def __init__(self, config: ASRConfig):
        try:
            import dashscope
            from dashscope.audio.qwen_omni import OmniRealtimeConversation
        except ImportError as exc:
            raise ASRError(
                "dashscope SDK not installed. Run: pip install 'dashscope>=1.25.6'"
            ) from exc

        if not config.api_key:
            raise ASRError("ASR api_key is empty.")

        dashscope.api_key = config.api_key
        self._ready = False
        self._session_created = False
        self._session_updated = False

        self.config = config
        self.conversation = None
        self.callback = None
        self._user_callback: Optional[Callable[..., None]] = None
        self._last_error: Optional[str] = None

    @property
    def ready(self) -> bool:
        return self._ready

    def _emit_text(self, text: str, is_final: bool, metadata: dict | None = None) -> None:
        if not text or not self._user_callback:
            return
        try:
            self._user_callback(text, is_final, metadata or {})
        except TypeError:
            self._user_callback(text, is_final)

    def _connect_conversation(self, conversation) -> None:
        try:
            import websocket
        except ImportError as exc:
            raise ASRError(
                "websocket-client is required for realtime ASR connection."
            ) from exc

        def _on_message(ws, message):
            conversation.on_message(ws, message)

        def _on_close(ws, close_status_code, close_msg):
            self._ready = False
            conversation.on_close(ws, close_status_code, close_msg)

        def _on_error(ws, error):
            self._ready = False
            self._last_error = f"connection closed: {error}"
            try:
                conversation.callback.on_close(None, str(error))
            except Exception:
                pass

        conversation.ws = websocket.WebSocketApp(
            conversation.url,
            header=conversation._get_websocket_header(),
            on_message=_on_message,
            on_error=_on_error,
            on_close=_on_close,
        )

        ping_interval = max(0.0, float(self.config.websocket_ping_interval_sec or 0.0))
        ping_timeout = None
        if ping_interval > 0:
            candidate_timeout = float(self.config.websocket_ping_timeout_sec or 0.0)
            if candidate_timeout > 0:
                ping_timeout = min(candidate_timeout, max(0.5, ping_interval - 0.5))

        run_kwargs: dict[str, float | str] = {}
        if ping_interval > 0:
            run_kwargs["ping_interval"] = ping_interval
            if ping_timeout is not None:
                run_kwargs["ping_timeout"] = ping_timeout
            run_kwargs["ping_payload"] = "keepalive"

        conversation.thread = threading.Thread(
            target=lambda: conversation.ws.run_forever(**run_kwargs),
            daemon=True,
        )
        conversation.thread.start()

        timeout = max(0.5, float(self.config.websocket_connect_timeout_sec or 10.0))
        start_time = time.time()
        while (
            not (conversation.ws.sock and conversation.ws.sock.connected)
            and (time.time() - start_time) < timeout
        ):
            time.sleep(0.1)
        if not (conversation.ws.sock and conversation.ws.sock.connected):
            raise TimeoutError(
                f"websocket connection could not established within {timeout:.1f}s. "
                "Please check your network connection, firewall settings, or server status."
            )
        conversation.callback.on_open()

    def start(self, callback: Callable[..., None]) -> None:
        try:
            from dashscope.audio.qwen_omni import (
                OmniRealtimeConversation,
                OmniRealtimeCallback,
                MultiModality,
            )
            from dashscope.audio.qwen_omni.omni_realtime import TranscriptionParams
        except ImportError as exc:
            raise ASRError(
                "dashscope SDK version is incompatible with qwen_omni realtime ASR."
            ) from exc

        self._user_callback = callback
        self._last_error = None
        self._ready = False
        self._session_created = False
        self._session_updated = False
        outer = self

        class ASRCallback(OmniRealtimeCallback):
            def on_open(self):
                pass

            def on_close(self, code, msg):
                outer._ready = False
                outer._last_error = f"connection closed: code={code}, msg={msg}"

            def on_error(self, error):
                outer._ready = False
                outer._last_error = f"ASR error: {error}"

            def on_event(self, response):
                try:
                    event_type = response.get("type", "")

                    if event_type == "session.created":
                        outer._session_created = True

                    elif event_type == "session.updated":
                        outer._session_updated = True
                        outer._ready = True

                    elif event_type == "conversation.item.input_audio_transcription.text":
                        text = (response.get("text", "") or "") + (response.get("stash", "") or "")
                        outer._emit_text(
                            text,
                            False,
                            {
                                "stability": response.get("stability"),
                                "start_ms": response.get("start_ms"),
                                "end_ms": response.get("end_ms"),
                            },
                        )

                    elif event_type == "conversation.item.input_audio_transcription.completed":
                        text = response.get("transcript", "") or ""
                        outer._emit_text(
                            text,
                            True,
                            {
                                "stability": 1.0,
                                "start_ms": response.get("start_ms"),
                                "end_ms": response.get("end_ms"),
                            },
                        )

                except Exception as exc:
                    outer._last_error = f"ASR callback parse error: {exc}"

        self.callback = ASRCallback()
        self.conversation = OmniRealtimeConversation(
            model=self.config.model,
            url=self.config.websocket_url,
            callback=self.callback,
        )

        self._connect_conversation(self.conversation)

        transcription_params = TranscriptionParams(
            language=self.config.language,
            sample_rate=self.config.sample_rate,
            input_audio_format=self.config.input_audio_format,
        )

        self.conversation.update_session(
            output_modalities=[MultiModality.TEXT],
            enable_input_audio_transcription=True,
            transcription_params=transcription_params,
            enable_turn_detection=self.config.enable_turn_detection,
            turn_detection_type="server_vad",
            turn_detection_threshold=self.config.turn_detection_threshold,
            turn_detection_silence_duration_ms=self.config.turn_detection_silence_duration_ms,
        )

    def send_audio(self, audio_data: bytes) -> None:
        if not self.conversation:
            raise ASRError("ASR not started")

        if not self._ready:
            # 会话还没 ready，直接丢弃或缓存
            return

        if not isinstance(audio_data, (bytes, bytearray)):
            raise ASRError(f"audio_data must be bytes-like, got {type(audio_data)}")

        if not audio_data:
            return

        if self._last_error:
            raise ASRError(self._last_error)

        # 官方示例是 3200 字节块
        if len(audio_data) < 3200:
            return

        try:
            audio_b64 = base64.b64encode(audio_data).decode("ascii")
            self.conversation.append_audio(audio_b64)
        except Exception as exc:
            raise ASRError(f"Failed to send audio: {exc}") from exc

    def commit(self) -> None:
        if not self.conversation:
            raise ASRError("ASR not started")

        if self._last_error:
            raise ASRError(self._last_error)

        try:
            self.conversation.commit()
        except Exception as exc:
            raise ASRError(f"Failed to commit audio input: {exc}") from exc

    def stop(self) -> None:
        """Finish ASR session."""
        self._ready = False
        if self.conversation:
            try:
                self.conversation.end_session()
            except Exception as exc:
                raise ASRError(f"Failed to end ASR session: {exc}") from exc
            finally:
                try:
                    self.conversation.close()
                except Exception:
                    pass
                self.conversation = None


def _normalize_provider(provider: str) -> str:
    value = str(provider or "qwen3_asr").strip().lower().replace("-", "_")
    if value in {"qwen", "qwen_asr", "qwen3", "qwen3_asr", "dashscope"}:
        return "qwen3_asr"
    if value in {"doubao", "dou_bao", "volc", "volcengine", "volcengine_doubao"}:
        return "dou_bao"
    return value


class StreamingASR:
    """Provider-dispatching ASR facade consumed by StreamingASRClient."""

    def __init__(self, config: ASRConfig):
        provider = _normalize_provider(config.provider)
        if provider == "qwen3_asr":
            self._impl = StreamingQwenASR(config)
            return
        if provider == "dou_bao":
            from .doubao_streaming import StreamingDoubaoASR

            self._impl = StreamingDoubaoASR(config)
            return
        raise ASRError(f"Unsupported ASR provider: {config.provider}")

    @property
    def ready(self) -> bool:
        return bool(self._impl.ready)

    def start(self, callback: Callable[..., None]) -> None:
        self._impl.start(callback)

    def send_audio(self, audio_data: bytes) -> None:
        self._impl.send_audio(audio_data)

    def commit(self) -> None:
        self._impl.commit()

    def stop(self) -> None:
        self._impl.stop()
