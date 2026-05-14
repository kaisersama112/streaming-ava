"""Speech post-processing entrypoints.

This package converts display text into text that is safer for TTS. The current
main use case is LaTeX/math oralization before streamed TTS submission.
"""

from .stream_buffer import LatexAwareSpeechBuffer
from .text_builder import SpeechBuildResult, build_speech_text, should_apply_math_oralizer

__all__ = [
    "LatexAwareSpeechBuffer",
    "SpeechBuildResult",
    "build_speech_text",
    "should_apply_math_oralizer",
]
