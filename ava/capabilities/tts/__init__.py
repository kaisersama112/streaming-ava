"""TTS capability facade."""

from ava.capabilities.tts.tts_rest_client import download_audio, synthesize
from ava.capabilities.tts.tts_streaming_sdk import (
    CosyVoiceSDKError,
    StreamingCosyVoice,
    synthesize_text,
)

__all__ = [
    "CosyVoiceSDKError",
    "StreamingCosyVoice",
    "download_audio",
    "synthesize",
    "synthesize_text",
]
