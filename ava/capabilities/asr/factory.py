"""Factory helpers for normalized streaming ASR providers."""

from __future__ import annotations

from typing import Any

from .asr_streaming_client import StreamingASRClient
from .asr_streaming_sdk import ASRConfig


def normalize_asr_provider(provider: str) -> str:
    value = str(provider or "qwen3_asr").strip().lower().replace("-", "_")
    if value in {"qwen", "qwen_asr", "qwen3", "qwen3_asr", "dashscope"}:
        return "qwen3_asr"
    if value in {"doubao", "dou_bao", "volc", "volcengine", "volcengine_doubao"}:
        return "dou_bao"
    return value


def _to_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump(exclude_none=True)
    return {}


def _fields_set(value: Any) -> set[str]:
    fields = getattr(value, "model_fields_set", set())
    return set(fields or set())


def _legacy(config: Any, name: str) -> tuple[bool, Any]:
    return name in _fields_set(config), getattr(config, name, None)


def _provider_value(config: Any, provider_obj: Any, name: str, legacy_name: str, default: Any) -> Any:
    if provider_obj is not None and name in _fields_set(provider_obj):
        value = getattr(provider_obj, name, None)
        if value not in (None, ""):
            return value
    has_legacy, legacy_value = _legacy(config, legacy_name)
    if has_legacy and legacy_value not in (None, ""):
        return legacy_value
    value = getattr(provider_obj, name, None) if provider_obj is not None else None
    if value not in (None, ""):
        return value
    return default


def _doubao_language(language: str) -> str:
    value = str(language or "").strip()
    aliases = {
        "zh": "zh-CN",
        "zh_cn": "zh-CN",
        "zh-cn": "zh-CN",
        "en": "en-US",
        "en_us": "en-US",
        "en-us": "en-US",
    }
    return aliases.get(value.lower(), value)


def build_asr_config(config: Any) -> ASRConfig:
    provider = normalize_asr_provider(getattr(config, "provider", "qwen3_asr"))
    qwen = getattr(config, "qwen3_asr", None)
    doubao = getattr(config, "dou_bao", None)

    if provider == "dou_bao":
        doubao_audio_obj = getattr(doubao, "audio", None)
        doubao_audio = _to_dict(doubao_audio_obj)
        doubao_request = _to_dict(getattr(doubao, "request", None))
        doubao_audio_fields = _fields_set(doubao_audio_obj)

        has_format, legacy_format = _legacy(config, "format")
        has_sample_rate, legacy_sample_rate = _legacy(config, "sample_rate")
        has_language, legacy_language = _legacy(config, "language")
        if has_format and legacy_format and "format" not in doubao_audio_fields:
            doubao_audio["format"] = legacy_format
        if has_sample_rate and legacy_sample_rate and "rate" not in doubao_audio_fields:
            doubao_audio["rate"] = int(legacy_sample_rate)
        if has_language and legacy_language and "language" not in doubao_audio_fields:
            doubao_audio["language"] = _doubao_language(str(legacy_language))

        sample_rate = int(doubao_audio.get("rate") or 16000)
        return ASRConfig(
            provider=provider,
            sample_rate=sample_rate,
            input_audio_format=str(doubao_audio.get("format") or "pcm"),
            language=str(doubao_audio.get("language") or "zh-CN"),
            websocket_connect_timeout_sec=float(
                getattr(doubao, "websocket_connect_timeout_sec", 10.0) or 10.0
            ),
            websocket_ping_interval_sec=float(
                getattr(doubao, "websocket_ping_interval_sec", 15.0) or 15.0
            ),
            websocket_ping_timeout_sec=float(
                getattr(doubao, "websocket_ping_timeout_sec", 8.0) or 8.0
            ),
            doubao_x_api_key=str(getattr(doubao, "x_api_key", "") or ""),
            doubao_resource_id=str(getattr(doubao, "x_api_resource_id", "") or "volc.seedasr.sauc.duration"),
            doubao_request_id=str(getattr(doubao, "x_api_request_id", "") or ""),
            doubao_ws_url=str(
                getattr(doubao, "ws_url", "") or "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async"
            ),
            doubao_uid=str(getattr(doubao, "uid", "") or "streaming_ava"),
            doubao_audio=doubao_audio,
            doubao_request=doubao_request,
        )

    return ASRConfig(
        provider="qwen3_asr",
        api_key=str(getattr(qwen, "api_key", "") or getattr(config, "api_key", "") or ""),
        model=str(_provider_value(config, qwen, "model", "model", "qwen3-asr-flash-realtime")),
        language=str(_provider_value(config, qwen, "language", "language", "zh")),
        sample_rate=int(_provider_value(config, qwen, "sample_rate", "sample_rate", 16000) or 16000),
        input_audio_format=str(_provider_value(config, qwen, "input_audio_format", "format", "pcm")),
        websocket_url=str(
            _provider_value(
                config,
                qwen,
                "websocket_url",
                "websocket_url",
                "wss://dashscope.aliyuncs.com/api-ws/v1/realtime",
            )
        ),
        websocket_connect_timeout_sec=float(
            _provider_value(config, qwen, "websocket_connect_timeout_sec", "websocket_connect_timeout_sec", 10.0)
            or 10.0
        ),
        websocket_ping_interval_sec=float(
            _provider_value(config, qwen, "websocket_ping_interval_sec", "websocket_ping_interval_sec", 15.0)
            or 15.0
        ),
        websocket_ping_timeout_sec=float(
            _provider_value(config, qwen, "websocket_ping_timeout_sec", "websocket_ping_timeout_sec", 8.0)
            or 8.0
        ),
        enable_turn_detection=bool(
            _provider_value(config, qwen, "enable_turn_detection", "enable_turn_detection", True)
        ),
        turn_detection_threshold=float(
            _provider_value(config, qwen, "turn_detection_threshold", "turn_detection_threshold", 0.45) or 0.45
        ),
        turn_detection_silence_duration_ms=int(
            _provider_value(
                config,
                qwen,
                "turn_detection_silence_duration_ms",
                "turn_detection_silence_duration_ms",
                850,
            )
            or 850
        ),
    )


def build_streaming_asr_client(config: Any) -> StreamingASRClient:
    return StreamingASRClient(build_asr_config(config))
