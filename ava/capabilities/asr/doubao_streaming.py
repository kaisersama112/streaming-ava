"""Doubao / Volcengine BigModel realtime ASR WebSocket adapter."""

from __future__ import annotations

import copy
import gzip
import json
import re
import threading
import time
import uuid
from typing import Any, Callable

from .asr_streaming_sdk import ASRConfig, ASRError

__all__ = ["StreamingDoubaoASR"]


class StreamingDoubaoASR:
    """Normalize Volcengine binary ASR responses into the common callback API."""

    _PROTOCOL_VERSION = 0x1
    _HEADER_SIZE_WORDS = 0x1

    _FULL_CLIENT_REQUEST = 0x1
    _AUDIO_ONLY_REQUEST = 0x2
    _FULL_SERVER_RESPONSE = 0x9
    _SERVER_ACK = 0xB
    _SERVER_ERROR_RESPONSE = 0xF

    _NO_SEQUENCE = 0x0
    _NEG_SEQUENCE = 0x2

    _NO_SERIALIZATION = 0x0
    _JSON = 0x1

    _NO_COMPRESSION = 0x0
    _GZIP = 0x1

    _SUCCESS_CODES = {None, 0, "0", 20000000, "20000000"}
    _COMMIT_FINAL_FALLBACK_SECONDS = 0.45

    def __init__(self, config: ASRConfig) -> None:
        try:
            import websocket
        except ImportError as exc:  # pragma: no cover
            raise ASRError("websocket-client is required for Doubao realtime ASR.") from exc

        if not config.doubao_x_api_key:
            raise ASRError("Doubao ASR x_api_key is empty.")
        if not config.doubao_resource_id:
            raise ASRError("Doubao ASR resource_id is empty.")

        self.config = config
        self._websocket = websocket
        self._ws = None
        self._thread: threading.Thread | None = None
        self._send_lock = threading.Lock()
        self._state_lock = threading.RLock()
        self._connection_open = threading.Event()
        self._ready_event = threading.Event()
        self._stopping = False
        self._ready = False
        self._committed = False
        self._error: Exception | None = None
        self._user_callback: Callable[..., None] | None = None
        self._last_partial_text = ""
        self._last_partial_metadata: dict[str, Any] = {}
        self._last_final_text = ""
        self._final_keys: set[tuple[int | None, int | None, str]] = set()
        self._commit_generation = 0

    @property
    def ready(self) -> bool:
        # After a negative/final packet the upstream may close the connection.
        # Returning true lets the outer client call send_audio(), where we can
        # lazily reconnect for the next utterance instead of letting audio sit
        # in the pending queue forever.
        return self._ready or (self._committed and not self._stopping)

    @classmethod
    def _header(
        cls,
        *,
        message_type: int,
        flags: int,
        serialization: int,
        compression: int,
    ) -> bytes:
        return bytes(
            [
                (cls._PROTOCOL_VERSION << 4) | cls._HEADER_SIZE_WORDS,
                (message_type << 4) | flags,
                (serialization << 4) | compression,
                0x00,
            ]
        )

    @classmethod
    def _frame(
        cls,
        *,
        message_type: int,
        flags: int,
        payload: bytes,
        serialization: int,
        compression: int,
    ) -> bytes:
        header = cls._header(
            message_type=message_type,
            flags=flags,
            serialization=serialization,
            compression=compression,
        )
        return header + len(payload).to_bytes(4, "big", signed=False) + payload

    @staticmethod
    def _strip_empty(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: stripped
                for key, item in value.items()
                if (stripped := StreamingDoubaoASR._strip_empty(item)) not in (None, "", [], {})
            }
        if isinstance(value, list):
            return [
                stripped
                for item in value
                if (stripped := StreamingDoubaoASR._strip_empty(item)) not in (None, "", [], {})
            ]
        return value

    def _headers(self) -> list[str]:
        return [
            f"X-Api-Key: {self.config.doubao_x_api_key}",
            f"X-Api-Resource-Id: {self.config.doubao_resource_id}",
            f"X-Api-Request-Id: {self.config.doubao_request_id or uuid.uuid4()}",
        ]

    def _request_payload(self) -> dict[str, Any]:
        audio = copy.deepcopy(self.config.doubao_audio or {})
        request = copy.deepcopy(self.config.doubao_request or {})
        extra = request.pop("extra", None)
        if isinstance(extra, dict):
            request.update(extra)
        return self._strip_empty(
            {
                "user": {"uid": self.config.doubao_uid or "streaming_ava"},
                "audio": audio,
                "request": request,
            }
        )

    def _full_client_request(self) -> bytes:
        payload = json.dumps(self._request_payload(), ensure_ascii=False).encode("utf-8")
        return self._frame(
            message_type=self._FULL_CLIENT_REQUEST,
            flags=self._NO_SEQUENCE,
            payload=gzip.compress(payload),
            serialization=self._JSON,
            compression=self._GZIP,
        )

    def _audio_request(self, audio_data: bytes, *, final: bool = False) -> bytes:
        if final:
            payload = b""
            flags = self._NEG_SEQUENCE
        else:
            payload = gzip.compress(bytes(audio_data))
            flags = self._NO_SEQUENCE
        return self._frame(
            message_type=self._AUDIO_ONLY_REQUEST,
            flags=flags,
            payload=payload,
            serialization=self._NO_SERIALIZATION,
            compression=self._GZIP,
        )

    @classmethod
    def _parse_message(cls, message: bytes) -> dict[str, Any]:
        if not isinstance(message, (bytes, bytearray)):
            raise ASRError(f"Doubao ASR expected binary message, got {type(message)}")
        raw = bytes(message)
        if len(raw) < 4:
            raise ASRError("Doubao ASR response is shorter than protocol header.")

        header_size = (raw[0] & 0x0F) * 4
        message_type = raw[1] >> 4
        flags = raw[1] & 0x0F
        serialization = raw[2] >> 4
        compression = raw[2] & 0x0F
        offset = header_size

        sequence: int | None = None
        if flags & 0x01:
            if len(raw) < offset + 4:
                raise ASRError("Doubao ASR response is missing sequence.")
            sequence = int.from_bytes(raw[offset : offset + 4], "big", signed=True)
            offset += 4

        if message_type == cls._SERVER_ERROR_RESPONSE:
            if len(raw) < offset + 8:
                raise ASRError("Doubao ASR error response is malformed.")
            code = int.from_bytes(raw[offset : offset + 4], "big", signed=False)
            offset += 4
            size = int.from_bytes(raw[offset : offset + 4], "big", signed=False)
            offset += 4
            detail = raw[offset : offset + size].decode("utf-8", errors="replace")
            return {
                "type": message_type,
                "flags": flags,
                "sequence": sequence,
                "is_final": bool((flags & cls._NEG_SEQUENCE) or (sequence is not None and sequence < 0)),
                "error": {"code": code, "message": detail},
            }

        payload: Any = None
        if len(raw) >= offset + 4:
            payload_size = int.from_bytes(raw[offset : offset + 4], "big", signed=False)
            offset += 4
            payload_bytes = raw[offset : offset + payload_size]
            if compression == cls._GZIP and payload_bytes:
                payload_bytes = gzip.decompress(payload_bytes)
            if serialization == cls._JSON and payload_bytes:
                payload = json.loads(payload_bytes.decode("utf-8"))
            elif payload_bytes:
                try:
                    payload = json.loads(payload_bytes.decode("utf-8"))
                except Exception:
                    payload = payload_bytes

        return {
            "type": message_type,
            "flags": flags,
            "sequence": sequence,
            "is_final": bool((flags & cls._NEG_SEQUENCE) or (sequence is not None and sequence < 0)),
            "payload": payload,
        }

    def _open_socket(self) -> None:
        self._connection_open.clear()
        self._ready_event.clear()
        self._ready = False
        self._error = None

        self._ws = self._websocket.WebSocketApp(
            self.config.doubao_ws_url,
            header=self._headers(),
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
        )
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

        timeout = max(0.5, float(self.config.websocket_connect_timeout_sec or 10.0))
        if not self._connection_open.wait(timeout=timeout):
            self._raise_or_error(f"Doubao ASR connection timed out after {timeout:.1f}s.")
        if not self._ready_event.wait(timeout=timeout):
            self._raise_or_error(f"Doubao ASR session init timed out after {timeout:.1f}s.")

    def _run(self) -> None:
        ping_interval = max(0.0, float(self.config.websocket_ping_interval_sec or 0.0))
        ping_timeout = None
        if ping_interval > 0:
            candidate_timeout = float(self.config.websocket_ping_timeout_sec or 0.0)
            if candidate_timeout > 0:
                ping_timeout = min(candidate_timeout, max(0.5, ping_interval - 0.5))
        kwargs: dict[str, Any] = {}
        if ping_interval > 0:
            kwargs["ping_interval"] = ping_interval
            if ping_timeout is not None:
                kwargs["ping_timeout"] = ping_timeout
            kwargs["ping_payload"] = "keepalive"
        self._ws.run_forever(**kwargs)

    def _send_binary(self, frame: bytes) -> None:
        if self._error is not None:
            raise ASRError(str(self._error))
        if self._ws is None:
            raise ASRError("Doubao ASR not started.")
        with self._send_lock:
            self._ws.send(frame, opcode=self._websocket.ABNF.OPCODE_BINARY)

    def _on_open(self, _ws) -> None:
        try:
            self._connection_open.set()
            self._send_binary(self._full_client_request())
            self._ready = True
            self._ready_event.set()
        except Exception as exc:
            self._error = ASRError(f"Doubao ASR session init failed: {exc}")
            self._ready_event.set()

    def _on_message(self, _ws, message) -> None:
        try:
            if isinstance(message, str):
                payload = json.loads(message)
                self._handle_payload(payload, sequence=None, final_response=bool(payload.get("is_final")))
                return

            parsed = self._parse_message(message)
            if parsed["type"] == self._SERVER_ERROR_RESPONSE:
                self._error = ASRError(f"Doubao ASR error: {parsed['error']}")
                self._ready = False
                return
            if parsed["type"] in {self._FULL_SERVER_RESPONSE, self._SERVER_ACK}:
                payload = parsed.get("payload")
                if isinstance(payload, dict):
                    self._handle_payload(
                        payload,
                        sequence=parsed.get("sequence"),
                        final_response=bool(parsed.get("is_final")),
                    )
        except Exception as exc:
            self._error = ASRError(f"Doubao ASR message parse failed: {exc}")
            self._ready = False

    def _on_error(self, _ws, error) -> None:
        if not self._stopping and not self._committed:
            self._error = ASRError(self._format_upstream_error(error))
        self._ready = False
        self._connection_open.set()
        self._ready_event.set()

    def _on_close(self, _ws, _code, _message) -> None:
        self._ready = False
        self._connection_open.set()
        self._ready_event.set()
        if not self._stopping and not self._committed and self._error is None:
            self._error = ASRError("Doubao ASR connection closed.")

    def _raise_or_error(self, fallback: str) -> None:
        if self._error is not None:
            raise ASRError(str(self._error))
        raise ASRError(fallback)

    def _format_upstream_error(self, error: Any) -> str:
        text = str(error)
        detail = ""
        match = re.search(r"b'(\{.*?\})'", text)
        if match:
            try:
                payload = json.loads(match.group(1))
                detail = str(payload.get("error") or payload.get("message") or "")
            except Exception:
                detail = ""
        lowered = f"{text} {detail}".lower()
        if "requested resource not granted" in lowered:
            return (
                "Doubao ASR resource is not granted: "
                f"X-Api-Resource-Id={self.config.doubao_resource_id!r}. "
                "Check that asr_config.dou_bao.x_api_key is the APP Key for the ASR app, "
                "and that this exact resource is enabled/granted in the Volcengine console. "
                "Common values: volc.seedasr.sauc.duration / volc.seedasr.sauc.concurrent "
                "for model 2.0, or volc.bigasr.sauc.duration / volc.bigasr.sauc.concurrent "
                f"for model 1.0. Upstream: {detail or text}"
            )
        if detail:
            return f"Doubao ASR upstream error: {detail}"
        return text

    def _emit_text(self, text: str, is_final: bool, metadata: dict[str, Any] | None = None) -> None:
        content = str(text or "").strip()
        if not content or not self._user_callback:
            return
        try:
            self._user_callback(content, is_final, metadata or {})
        except TypeError:
            self._user_callback(content, is_final)

    @staticmethod
    def _first_text(*values: Any) -> str:
        for value in values:
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    @staticmethod
    def _as_int(value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except Exception:
            return None

    @staticmethod
    def _first_present(*values: Any) -> Any:
        for value in values:
            if value is not None:
                return value
        return None

    def _emit_final_once(self, text: str, metadata: dict[str, Any] | None = None) -> None:
        content = str(text or "").strip()
        if not content or content == self._last_final_text:
            return
        self._last_final_text = content
        final_metadata = {"stability": 1.0}
        final_metadata.update(metadata or {})
        self._emit_text(content, True, final_metadata)

    def _emit_partial(self, text: str, metadata: dict[str, Any] | None = None) -> None:
        content = str(text or "").strip()
        if not content or content == self._last_partial_text:
            return
        self._last_partial_text = content
        self._last_partial_metadata = dict(metadata or {})
        self._emit_text(content, False, self._last_partial_metadata)
        if self._committed and not self._stopping:
            self._schedule_commit_final_fallback()

    def _emit_pending_final_from_partial(self) -> None:
        if not self._last_partial_text:
            return
        self._emit_final_once(self._last_partial_text, self._last_partial_metadata)

    def _schedule_commit_final_fallback(self) -> None:
        with self._state_lock:
            self._commit_generation += 1
            generation = self._commit_generation
        thread = threading.Thread(target=self._commit_final_fallback, args=(generation,), daemon=True)
        thread.start()

    def _commit_final_fallback(self, generation: int) -> None:
        time.sleep(self._COMMIT_FINAL_FALLBACK_SECONDS)
        with self._state_lock:
            if self._stopping or not self._committed or generation != self._commit_generation:
                return
            if not self._last_partial_text or self._last_partial_text == self._last_final_text:
                return
            self._emit_pending_final_from_partial()

    def _utterance_span(self, utterances: Any) -> tuple[int | None, int | None]:
        if not isinstance(utterances, list):
            return None, None
        starts: list[int] = []
        ends: list[int] = []
        for utterance in utterances:
            if not isinstance(utterance, dict):
                continue
            start = self._as_int(self._first_present(utterance.get("start_time"), utterance.get("start_ms")))
            end = self._as_int(self._first_present(utterance.get("end_time"), utterance.get("end_ms")))
            if start is not None:
                starts.append(start)
            if end is not None:
                ends.append(end)
        return (min(starts) if starts else None, max(ends) if ends else None)

    def _handle_payload(
        self,
        payload: dict[str, Any],
        *,
        sequence: int | None,
        final_response: bool = False,
    ) -> None:
        code = payload.get("code")
        if code not in self._SUCCESS_CODES:
            self._error = ASRError(str(payload))
            self._ready = False
            return

        result = payload.get("result") or payload.get("results")
        if result is None and any(key in payload for key in ("text", "transcript", "utterances")):
            result = payload
        results = result if isinstance(result, list) else [result]
        final_by_sequence = bool(final_response or (sequence is not None and sequence < 0))

        for item in results:
            if not isinstance(item, dict):
                continue
            emitted = False
            utterances = item.get("utterances") or item.get("utterance") or []
            aggregate_text = self._first_text(item.get("text"), item.get("transcript"), payload.get("text"))
            start_ms, end_ms = self._utterance_span(utterances)
            aggregate_metadata = {
                key: value
                for key, value in {"stability": None, "start_ms": start_ms, "end_ms": end_ms}.items()
                if value is not None
            }
            if final_by_sequence and aggregate_text:
                metadata = {
                    key: value
                    for key, value in {"start_ms": start_ms, "end_ms": end_ms}.items()
                    if value is not None
                }
                self._emit_final_once(aggregate_text, metadata)
                continue
            if aggregate_text:
                self._emit_partial(aggregate_text, aggregate_metadata)
                emitted = True

            if not aggregate_text and isinstance(utterances, list):
                for utterance in utterances:
                    if not isinstance(utterance, dict):
                        continue
                    text = self._first_text(utterance.get("text"), utterance.get("result"))
                    if not text:
                        continue
                    start_ms = self._as_int(self._first_present(utterance.get("start_time"), utterance.get("start_ms")))
                    end_ms = self._as_int(self._first_present(utterance.get("end_time"), utterance.get("end_ms")))
                    is_final = bool(
                        utterance.get("definite")
                        or utterance.get("is_final")
                        or utterance.get("final")
                        or final_by_sequence
                    )
                    if is_final:
                        key = (start_ms, end_ms, text)
                        if key not in self._final_keys:
                            self._final_keys.add(key)
                            self._emit_final_once(text, {"start_ms": start_ms, "end_ms": end_ms})
                        emitted = True
                    else:
                        self._emit_partial(text, {"stability": None, "start_ms": start_ms, "end_ms": end_ms})
                        emitted = True

            if emitted:
                continue

            text = aggregate_text
            if not text:
                continue
            is_final = bool(item.get("definite") or item.get("is_final") or payload.get("is_final") or final_by_sequence)
            if is_final:
                self._emit_final_once(text)
            else:
                self._emit_partial(text, {"stability": None})

    def start(self, callback: Callable[..., None]) -> None:
        self._user_callback = callback
        self._stopping = False
        self._committed = False
        self._last_partial_text = ""
        self._last_partial_metadata = {}
        self._last_final_text = ""
        self._final_keys.clear()
        self._commit_generation += 1
        self._open_socket()

    def _restart_after_commit(self) -> None:
        with self._state_lock:
            old_ws = self._ws
            old_thread = self._thread
            previous_stopping = self._stopping
            self._stopping = True
            self._ready = False
            if old_ws is not None:
                try:
                    old_ws.close()
                except Exception:
                    pass
            if old_thread is not None and old_thread is not threading.current_thread():
                old_thread.join(timeout=1.0)
            self._stopping = previous_stopping
            self._committed = False
            self._commit_generation += 1
            self._open_socket()

    def send_audio(self, audio_data: bytes) -> None:
        if not isinstance(audio_data, (bytes, bytearray)):
            raise ASRError(f"audio_data must be bytes-like, got {type(audio_data)}")
        if not audio_data:
            return
        if self._committed:
            self._restart_after_commit()
        if not self._ready:
            return
        self._send_binary(self._audio_request(bytes(audio_data), final=False))

    def commit(self) -> None:
        if self._committed:
            return
        if self._error is not None:
            raise ASRError(str(self._error))
        self._send_binary(self._audio_request(b"", final=True))
        self._committed = True
        self._schedule_commit_final_fallback()

    def stop(self) -> None:
        self._stopping = True
        self._ready = False
        try:
            if self._ws is not None:
                self._ws.close()
        except Exception:
            pass
        finally:
            self._ws = None
