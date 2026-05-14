"""Doubao / Volcengine TTS streaming adapter."""

from __future__ import annotations

import base64
import copy
import json
import queue
import time
import uuid
from typing import Any

import requests

from ava.capabilities.tts.base import TTSError, TTSRuntimeOptions


__all__ = [
    "StreamingDoubaoTTS",
]


class StreamingDoubaoTTS:
    """Normalize Doubao TTS V3 SSE responses into PCM chunk queues."""

    _SUCCESS_CODES = {None, 0, "0", 20000000, "20000000"}

    def __init__(
            self,
            *,
            x_api_key: str,
            x_api_resource_id: str,
            sse_url: str,
            model: str,
            req_params: Any | dict[str, Any] | None = None,
            options: TTSRuntimeOptions | None = None,
            fallback_speaker: str = "",
    ) -> None:
        if not x_api_key:
            raise TTSError("Doubao app_id is empty.")
        if not x_api_resource_id:
            raise TTSError("Doubao access_key is empty.")
        self._req_params = self._normalize_req_params(
            req_params=req_params,
            fallback_model=model,
            fallback_speaker=fallback_speaker,
            options=options or TTSRuntimeOptions(),
        )
        if not self._req_params.get("speaker"):
            raise TTSError("Doubao speaker is empty.")
        self._x_api_key = x_api_key
        self._x_api_resource_id = x_api_resource_id or model or "seed-tts-2.0"
        self._sse_url = sse_url or "https://openspeech.bytedance.com/api/v3/tts/unidirectional/sse"
        self._chunks: queue.Queue[bytes] = queue.Queue()
        self._error: Exception | None = None
        self._done = False

    @staticmethod
    def _rate_to_percent(rate: float) -> int:
        return max(-50, min(100, int(round((float(rate or 1.0) - 1.0) * 100))))

    @staticmethod
    def _volume_to_percent(volume: int) -> int:
        # Existing config uses 50 as neutral for CosyVoice volume.
        return max(-50, min(100, int(round(((float(volume or 50) / 50.0) - 1.0) * 100))))

    @classmethod
    def _normalize_req_params(
        cls,
        *,
        req_params: Any | dict[str, Any] | None,
        fallback_model: str,
        fallback_speaker: str,
        options: TTSRuntimeOptions,
    ) -> dict[str, Any]:
        configured = bool(req_params)
        base = cls._to_plain_dict(req_params)
        if not str(base.get("speaker") or "").strip():
            base["speaker"] = fallback_speaker
        if not str(base.get("model") or "").strip() and fallback_model:
            base["model"] = fallback_model
        if not cls._to_plain_dict(base.get("audio_params")):
            base["audio_params"] = {
                "format": options.audio_format or "pcm",
                "sample_rate": options.sample_rate,
                "speech_rate": cls._rate_to_percent(options.speech_rate),
                "loudness_rate": cls._volume_to_percent(options.volume),
            }
        elif configured:
            base["audio_params"] = cls._to_plain_dict(base.get("audio_params"))
        additions = cls._configured_additions(req_params, base)
        if additions:
            base["additions"] = additions
        else:
            base.pop("additions", None)
        return base

    @staticmethod
    def _to_plain_dict(value: Any, *, exclude_defaults: bool = False) -> dict[str, Any]:
        if value is None:
            return {}
        if isinstance(value, dict):
            return copy.deepcopy(value)
        model_dump = getattr(value, "model_dump", None)
        if callable(model_dump):
            return model_dump(exclude_none=True, exclude_defaults=exclude_defaults)
        return {}

    @classmethod
    def _configured_additions(cls, req_params: Any, base: dict[str, Any]) -> dict[str, Any]:
        if isinstance(req_params, dict):
            return cls._to_plain_dict(req_params.get("additions"))
        additions = getattr(req_params, "additions", None)
        if additions is not None:
            return cls._to_plain_dict(additions, exclude_defaults=True)
        return cls._to_plain_dict(base.get("additions"))

    def _headers(self) -> dict[str, str]:
        return {
            "X-Api-Key": self._x_api_key,
            "X-Api-Resource-Id": self._x_api_resource_id,
        }

    @staticmethod
    def _strip_empty(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: stripped
                for key, item in value.items()
                if (stripped := StreamingDoubaoTTS._strip_empty(item)) not in (None, "", [], {})
            }
        if isinstance(value, list):
            return [
                stripped
                for item in value
                if (stripped := StreamingDoubaoTTS._strip_empty(item)) not in (None, "", [], {})
            ]
        return value

    def _payload(self, text: str) -> dict[str, object]:
        req_params = copy.deepcopy(self._req_params)
        if text:
            req_params["text"] = text
        additions = self._to_plain_dict(req_params.get("additions"))
        if isinstance(additions, dict):
            additions = self._strip_empty(
                {
                    key: value
                    for key, value in additions.items()
                    if value not in (None, "", [], {})
                }
            )
            if additions:
                req_params["additions"] = json.dumps(additions, ensure_ascii=False)
            else:
                req_params.pop("additions", None)
        req_params = self._strip_empty(req_params)

        return {
            "user": {"uid": f"streaming_ava_{uuid.uuid4().hex[:16]}"},
            "req_params": req_params,
        }

    def _push_audio_from_payload(self, payload: object) -> None:
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except Exception:
                return
        if not isinstance(payload, dict):
            return
        if payload.get("code") not in self._SUCCESS_CODES:
            self._error = TTSError(str(payload))
            return
        data = payload.get("data")
        result = payload.get("result")
        candidates = [
            payload.get("audio"),
            data,
            payload.get("audio_data"),
            data.get("audio") if isinstance(data, dict) else None,
            data.get("audio_data") if isinstance(data, dict) else None,
            result.get("audio") if isinstance(result, dict) else None,
            result.get("audio_data") if isinstance(result, dict) else None,
        ]
        for candidate in candidates:
            if isinstance(candidate, str) and candidate:
                try:
                    self._chunks.put(base64.b64decode(candidate))
                    return
                except Exception:
                    continue

    def feed(self, text: str) -> None:
        content = str(text or "").strip()
        if not content:
            return
        try:
            with requests.post(
                    self._sse_url,
                    headers=self._headers(),
                    json=self._payload(content),
                    stream=True,
                    timeout=120,
            ) as resp:
                if resp.status_code >= 400:
                    raise TTSError(f"Doubao TTS request failed ({resp.status_code}): {resp.text}")
                for raw_line in resp.iter_lines(decode_unicode=True):
                    if not raw_line:
                        continue
                    line = str(raw_line).strip()
                    if line.startswith("data:"):
                        line = line[5:].strip()
                    if line in {"[DONE]", "DONE"}:
                        break
                    self._push_audio_from_payload(line)
                    if self._error is not None:
                        raise self._error
        except Exception as exc:
            self._error = TTSError(str(exc))
            raise self._error

    def complete(self, timeout_millis: int = 120000) -> None:
        deadline = time.monotonic() + max(0.001, timeout_millis / 1000.0)
        while time.monotonic() < deadline:
            if self._chunks.empty():
                break
            time.sleep(0.01)
        self._done = True

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
