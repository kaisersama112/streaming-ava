"""Factory for normalized streaming TTS providers."""

from __future__ import annotations

from typing import Any

from ava.capabilities.tts.base import StreamingTTSClient, TTSError, TTSRuntimeOptions
from ava.capabilities.tts.doubao_streaming import StreamingDoubaoTTS
from ava.capabilities.tts.stepfun_streaming import StreamingStepFunTTS
from ava.capabilities.tts.cosyvoice_streaming_sdk import CosyVoiceSDKError, StreamingCosyVoice


def _runtime_options(config: object, *, audio_format: str | None = None,
                     sample_rate: int | None = None) -> TTSRuntimeOptions:
    return TTSRuntimeOptions(
        audio_format=audio_format or getattr(config, "format", "pcm") or "pcm" or "pcm",
        sample_rate=int(sample_rate or getattr(config, "sample_rate", 24000) or 24000),
        volume=int(getattr(config, "volume", 50) or 50),
        speech_rate=float(getattr(config, "speech_rate", 1.0) or 1.0),
        pitch_rate=float(getattr(config, "pitch_rate", 1.0) or 1.0),
    )


def build_streaming_tts(
        config: object,
        *,
        audio_format: str | None = None,
        sample_rate: int | None = None,
) -> StreamingTTSClient:
    provider = getattr(config, "provider", "cosyvoice") or "cosyvoice"
    options = _runtime_options(config, audio_format=audio_format, sample_rate=sample_rate)

    if provider in {"cosyvoice"}:
        cosyvoice = getattr(config, "cosyvoice")
        return StreamingCosyVoice(
            api_key=cosyvoice.api_key,
            model=cosyvoice.model,
            voice=cosyvoice.voice,
            volume=options.volume,
            speech_rate=options.speech_rate,
            pitch_rate=options.pitch_rate,
            instruction=cosyvoice.instruction,
            audio_format=options.audio_format,
            sample_rate=options.sample_rate,
        )

    if provider in {"step_fun"}:
        step_fun = getattr(config, "step_fun")
        fallback_voice = getattr(getattr(config, "cosyvoice"), "voice", "")
        fallback_instruction = getattr(getattr(config, "cosyvoice"), "instruction", "")
        return StreamingStepFunTTS(
            api_key=step_fun.api_key,
            ws_url=step_fun.ws_url,
            model=step_fun.model,
            voice=step_fun.voice or fallback_voice,
            instruction=step_fun.instruction or fallback_instruction,
            options=options,
        )

    if provider in {"dou_bao"}:
        dou_bao = getattr(config, "dou_bao")
        fallback_speaker = getattr(getattr(config, "cosyvoice"), "voice", "")
        return StreamingDoubaoTTS(
            x_api_key=dou_bao.x_api_key,
            x_api_resource_id=dou_bao.x_api_resource_id,
            sse_url=dou_bao.sse_url,
            req_params=dou_bao.req_params,
            options=options,
            fallback_speaker=fallback_speaker,
        )

    raise TTSError(f"Unsupported TTS provider: {getattr(config, 'provider', '')}")


def normalize_tts_error(exc: Exception) -> TTSError:
    if isinstance(exc, TTSError):
        return exc
    if isinstance(exc, CosyVoiceSDKError):
        return TTSError(str(exc))
    return TTSError(str(exc))
