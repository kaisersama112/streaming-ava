"""TTS capability facade."""

from ava.capabilities.tts.base import StreamingTTSClient, TTSError, TTSRuntimeOptions
from ava.capabilities.tts.tts_rest_client import download_audio, synthesize
from ava.capabilities.tts.tts_streaming_sdk import (
    CosyVoiceSDKError,
    StreamingCosyVoice,
    synthesize_text,
)


def __getattr__(name: str):
    if name == "build_streaming_tts":
        from ava.capabilities.tts.factory import build_streaming_tts

        return build_streaming_tts
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "CosyVoiceSDKError",
    "StreamingTTSClient",
    "StreamingCosyVoice",
    "TTSError",
    "TTSRuntimeOptions",
    "build_streaming_tts",
    "download_audio",
    "synthesize",
    "synthesize_text",
]
