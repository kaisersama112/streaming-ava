"""Factory for normalized streaming TTS providers."""

from __future__ import annotations

from typing import Any

from ava.capabilities.tts.base import StreamingTTSClient, TTSError, TTSRuntimeOptions
from ava.capabilities.tts.doubao_streaming import StreamingDoubaoTTS
from ava.capabilities.tts.stepfun_streaming import StreamingStepFunTTS
from ava.capabilities.tts.tts_streaming_sdk import CosyVoiceSDKError, StreamingCosyVoice


def _clean_config_string(value: object) -> str:
    text = str(value or "").strip()
    # Be tolerant of accidental YAML values copied from Python annotations,
    # for example: key: str = "value".
    if text.startswith("str = "):
        text = text.split("=", 1)[1].strip()
    if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
        text = text[1:-1]
    return text.strip()


def _get(value: object, name: str, default: Any = None) -> Any:
    return getattr(value, name, default)


def _runtime_options(config: object, *, audio_format: str | None = None, sample_rate: int | None = None) -> TTSRuntimeOptions:
    return TTSRuntimeOptions(
        audio_format=_clean_config_string(audio_format or _get(config, "format", "pcm") or "pcm").lower() or "pcm",
        sample_rate=int(sample_rate or _get(config, "sample_rate", 24000) or 24000),
        volume=int(_get(config, "volume", 50) or 50),
        speech_rate=float(_get(config, "speech_rate", 1.0) or 1.0),
        pitch_rate=float(_get(config, "pitch_rate", 1.0) or 1.0),
    )


def build_streaming_tts(
    config: object,
    *,
    audio_format: str | None = None,
    sample_rate: int | None = None,
) -> StreamingTTSClient:
    provider = _clean_config_string(_get(config, "provider", "cosyvoice") or "cosyvoice").lower()
    options = _runtime_options(config, audio_format=audio_format, sample_rate=sample_rate)

    if provider in {"cosyvoice", "ali", "aliyun", "dashscope"}:
        cosyvoice = _get(config, "cosyvoice")
        return StreamingCosyVoice(
            api_key=_clean_config_string(cosyvoice.api_key),
            model=_clean_config_string(cosyvoice.model),
            voice=_clean_config_string(cosyvoice.voice),
            volume=options.volume,
            speech_rate=options.speech_rate,
            pitch_rate=options.pitch_rate,
            instruction=cosyvoice.instruction,
            audio_format=options.audio_format,
            sample_rate=options.sample_rate,
        )

    if provider in {"stepfun", "step_fun", "step"}:
        step_fun = _get(config, "step_fun")
        fallback_voice = _get(_get(config, "cosyvoice"), "voice", "")
        fallback_instruction = _get(_get(config, "cosyvoice"), "instruction", "")
        return StreamingStepFunTTS(
            api_key=_clean_config_string(step_fun.api_key),
            ws_url=_clean_config_string(step_fun.ws_url),
            model=_clean_config_string(step_fun.model),
            voice=_clean_config_string(step_fun.voice or fallback_voice),
            instruction=step_fun.instruction or fallback_instruction,
            options=options,
        )

    if provider in {"doubao", "dou_bao", "volcengine", "volc"}:
        dou_bao = _get(config, "dou_bao")
        fallback_speaker = _get(_get(config, "cosyvoice"), "voice", "")
        return StreamingDoubaoTTS(
            x_api_key=_clean_config_string(dou_bao.x_api_key),
            x_api_resource_id=_clean_config_string(dou_bao.x_api_resource_id),
            sse_url=_clean_config_string(dou_bao.sse_url),
            model=_clean_config_string(dou_bao.model or dou_bao.x_api_resource_id),
            req_params=dou_bao.req_params,
            options=options,
            fallback_speaker=_clean_config_string(fallback_speaker),
        )

    raise TTSError(f"Unsupported TTS provider: {_get(config, 'provider', '')}")


def normalize_tts_error(exc: Exception) -> TTSError:
    if isinstance(exc, TTSError):
        return exc
    if isinstance(exc, CosyVoiceSDKError):
        return TTSError(str(exc))
    return TTSError(str(exc))
