"""StepFun streaming TTS WebSocket adapter."""

from __future__ import annotations

import base64
import json
import queue
import threading
import time
import uuid
from urllib.parse import urlencode

from ava.capabilities.tts.base import TTSError, TTSRuntimeOptions


class StreamingStepFunTTS:
    """Normalize StepFun TTS WebSocket events into PCM chunk queues."""

    def __init__(
        self,
        *,
        api_key: str,
        ws_url: str,
        model: str,
        voice: str,
        instruction: str,
        options: TTSRuntimeOptions | None = None,
    ) -> None:
        try:
            import websocket
        except ImportError as exc:  # pragma: no cover
            raise TTSError("websocket-client is required for StepFun TTS.") from exc

        if not api_key:
            raise TTSError("StepFun api_key is empty.")
        if not model:
            raise TTSError("StepFun model is empty.")
        if not voice:
            raise TTSError("StepFun voice is empty.")

        self._websocket = websocket
        self._api_key = api_key
        self._ws_url = ws_url.rstrip("?")
        self._model = model
        self._voice = voice
        self._instruction = instruction
        self._options = options or TTSRuntimeOptions()
        self._chunks: queue.Queue[bytes] = queue.Queue()
        self._done = threading.Event()
        self._created = threading.Event()
        self._connection_ready = threading.Event()
        self._send_lock = threading.Lock()
        self._error: Exception | None = None
        self._session_id = ""
        self._ws = self._build_ws()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        if not self._connection_ready.wait(timeout=8):
            self._raise_or_error("StepFun TTS connection timed out.")
        if not self._created.wait(timeout=8):
            self._raise_or_error("StepFun TTS session create timed out.")

    def _url(self) -> str:
        sep = "&" if "?" in self._ws_url else "?"
        return f"{self._ws_url}{sep}{urlencode({'model': self._model})}"

    def _build_ws(self):
        return self._websocket.WebSocketApp(
            self._url(),
            header={"Authorization": f"Bearer {self._api_key}"},
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
        )

    def _run(self) -> None:
        self._ws.run_forever()

    def _send_json(self, payload: dict[str, object]) -> None:
        if self._error is not None:
            raise TTSError(str(self._error))
        with self._send_lock:
            self._ws.send(json.dumps(payload, ensure_ascii=False))

    def _create_session(self) -> None:
        volume_ratio = max(0.1, min(2.0, float(self._options.volume or 50) / 50.0))
        speed_ratio = max(0.5, min(2.0, float(self._options.speech_rate or 1.0)))
        data: dict[str, object] = {
            "session_id": self._session_id,
            "voice_id": self._voice,
            "response_format": self._options.audio_format,
            "sample_rate": self._options.sample_rate,
            "volume_ratio": volume_ratio,
            "speed_ratio": speed_ratio,
            "mode": "default",
        }
        if self._instruction:
            data["instruction"] = self._instruction[:200]
        self._send_json({"type": "tts.create", "data": data})

    def _on_message(self, _ws, message: str) -> None:
        try:
            payload = json.loads(message)
            event_type = str(payload.get("type") or "")
            data = dict(payload.get("data") or {})
            if event_type == "tts.connection.done":
                self._session_id = str(data.get("session_id") or uuid.uuid4().hex)
                self._connection_ready.set()
                self._create_session()
                return
            if event_type == "tts.response.created":
                self._created.set()
                return
            if event_type == "tts.response.audio.delta":
                audio = data.get("audio") or data.get("delta") or data.get("content")
                if isinstance(audio, str) and audio:
                    self._chunks.put(base64.b64decode(audio))
                return
            if event_type in {"tts.response.audio.done", "response.audio.done"}:
                self._done.set()
                return
            if event_type == "tts.response.error":
                self._error = TTSError(str(data or payload))
                self._done.set()
        except Exception as exc:
            self._error = TTSError(f"StepFun TTS message parse failed: {exc}")
            self._done.set()

    def _on_error(self, _ws, error) -> None:
        self._error = TTSError(str(error))
        self._done.set()
        self._connection_ready.set()
        self._created.set()

    def _on_close(self, _ws, _code, _message) -> None:
        self._done.set()

    def _raise_or_error(self, fallback: str) -> None:
        if self._error is not None:
            raise TTSError(str(self._error))
        raise TTSError(fallback)

    def feed(self, text: str) -> None:
        content = str(text or "").strip()
        if not content or self._done.is_set():
            return
        self._created.wait(timeout=8)
        self._send_json({"type": "tts.text.delta", "data": {"session_id": self._session_id, "text": content[:1000]}})

    def complete(self, timeout_millis: int = 120000) -> None:
        if self._done.is_set():
            return
        try:
            if self._session_id:
                self._send_json({"type": "tts.text.flush", "data": {"session_id": self._session_id}})
                self._send_json({"type": "tts.text.done", "data": {"session_id": self._session_id}})
            self._done.wait(timeout=max(0.001, timeout_millis / 1000.0))
        finally:
            try:
                self._ws.close()
            except Exception:
                pass

    def pop_chunks(self) -> list[bytes]:
        out: list[bytes] = []
        while True:
            try:
                chunk = self._chunks.get_nowait()
            except queue.Empty:
                break
            if chunk:
                out.append(chunk)
        return out
