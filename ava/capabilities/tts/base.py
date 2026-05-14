"""Shared TTS provider contracts."""

from dataclasses import dataclass
from typing import Protocol


class TTSError(RuntimeError):
    """Normalized TTS provider error."""


@dataclass(frozen=True)
class TTSRuntimeOptions:
    """Provider-neutral runtime knobs for streaming TTS."""

    audio_format: str = "pcm"
    sample_rate: int = 24000
    volume: int = 50
    speech_rate: float = 1.0
    pitch_rate: float = 1.0


class StreamingTTSClient(Protocol):
    """Common streaming TTS surface consumed by StreamingVoicePipeline."""

    def feed(self, text: str) -> None:
        """Submit text for synthesis."""

    def complete(self, timeout_millis: int = 120000) -> None:
        """Signal that no more text will be submitted."""

    def pop_chunks(self) -> list[bytes]:
        """Return provider audio chunks as PCM S16LE mono bytes."""
