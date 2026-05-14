"""ASR capability facade."""

from .asr_recognize import recognize_text
from .asr_streaming_client import ASRResult, StreamingASRClient
from .asr_streaming_sdk import ASRConfig, ASRError, StreamingASR
from .factory import build_asr_config, build_streaming_asr_client, normalize_asr_provider

__all__ = [
    "ASRConfig",
    "ASRError",
    "StreamingASR",
    "StreamingASRClient",
    "ASRResult",
    "build_asr_config",
    "build_streaming_asr_client",
    "normalize_asr_provider",
    "recognize_text",
]
