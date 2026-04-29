"""Voice interaction service for speech-to-text and text-to-speech integration."""

from __future__ import annotations

import threading
import queue
import time
from dataclasses import dataclass
from typing import Optional, Callable

from ava.infrastructure.asr import ASRConfig, StreamingASR, ASRError
from ava.infrastructure.tts.streaming_sdk import StreamingCosyVoice, CosyVoiceSDKError
from ava.application.voice_stream import VoiceStreamConfig


@dataclass(frozen=True)
class VoiceInteractionConfig:
    """Voice interaction configuration."""
    asr_api_key: str
    asr_model: str = "fun-asr-realtime"
    asr_format: str = "pcm"
    asr_sample_rate: int = 16000
    asr_language: str = "zh"
    tts_api_key: str = ""
    tts_model: str = "cosyvoice-v3-flash"
    tts_voice: str = "longxiaoxia_v3"
    tts_volume: int = 50
    tts_speech_rate: float = 1.0
    tts_pitch_rate: float = 1.0
    tts_instruction: str = ""
    tts_audio_format: str = "pcm"
    tts_sample_rate: int = 24000


class VoiceInteractionService:
    """Service for voice interaction with ASR and TTS."""

    def __init__(self, config: VoiceInteractionConfig):
        self.config = config
        self.asr: Optional[StreamingASR] = None
        self.tts: Optional[StreamingCosyVoice] = None
        self.audio_queue: queue.Queue[bytes] = queue.Queue()
        self.text_queue: queue.Queue[str] = queue.Queue()
        self.is_running = False
        self.thread: Optional[threading.Thread] = None
        self.callback: Optional[Callable[[str], None]] = None

    def start(self, callback: Callable[[str], None]) -> None:
        """Start voice interaction service.
        
        Args:
            callback: Function to call with recognized text.
        """
        self.callback = callback
        self.is_running = True
        
        # Initialize ASR
        try:
            asr_config = ASRConfig(
                api_key=self.config.asr_api_key,
                model=self.config.asr_model,
                input_audio_format=self.config.asr_format,
                sample_rate=self.config.asr_sample_rate,
                language=self.config.asr_language
            )
            self.asr = StreamingASR(asr_config)
        except ASRError as e:
            raise RuntimeError(f"Failed to initialize ASR: {e}")

        # Initialize TTS if API key is provided
        if self.config.tts_api_key:
            try:
                tts_config = VoiceStreamConfig(
                    api_key=self.config.tts_api_key,
                    model=self.config.tts_model,
                    voice=self.config.tts_voice,
                    volume=self.config.tts_volume,
                    speech_rate=self.config.tts_speech_rate,
                    pitch_rate=self.config.tts_pitch_rate,
                    instruction=self.config.tts_instruction,
                    audio_format=self.config.tts_audio_format,
                    sample_rate=self.config.tts_sample_rate
                )
                self.tts = StreamingCosyVoice(
                    api_key=tts_config.api_key,
                    model=tts_config.model,
                    voice=tts_config.voice,
                    volume=tts_config.volume,
                    speech_rate=tts_config.speech_rate,
                    pitch_rate=tts_config.pitch_rate,
                    instruction=tts_config.instruction,
                    audio_format=tts_config.audio_format,
                    sample_rate=tts_config.sample_rate
                )
            except CosyVoiceSDKError as e:
                raise RuntimeError(f"Failed to initialize TTS: {e}")

        # Start ASR callback thread
        def asr_callback(text: str, is_final: bool):
            if is_final and text:
                self.text_queue.put(text)
                if self.callback:
                    self.callback(text)

        self.asr.start(asr_callback)

        # Start audio processing thread
        def process_audio():
            while self.is_running:
                try:
                    audio_data = self.audio_queue.get(timeout=0.1)
                    if audio_data:
                        self.asr.send_audio(audio_data)
                except queue.Empty:
                    continue
                except Exception as e:
                    print(f"Error processing audio: {e}")

        self.thread = threading.Thread(target=process_audio, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        """Stop voice interaction service."""
        self.is_running = False
        if self.thread:
            self.thread.join(timeout=2.0)
        if self.asr:
            self.asr.stop()
        self.asr = None
        self.tts = None

    def send_audio(self, audio_data: bytes) -> None:
        """Send audio data for recognition.
        
        Args:
            audio_data: Audio data in PCM format.
        """
        if self.is_running and self.asr:
            self.audio_queue.put(audio_data)

    def speak(self, text: str) -> list[bytes]:
        """Convert text to speech.
        
        Args:
            text: Text to convert to speech.
        
        Returns:
            List of audio chunks.
        """
        if not self.tts:
            raise RuntimeError("TTS not initialized")
        
        self.tts.feed(text)
        self.tts.complete()
        return self.tts.pop_chunks()

    def get_recognized_text(self, timeout: float = 1.0) -> Optional[str]:
        """Get recognized text from queue.
        
        Args:
            timeout: Timeout in seconds.
        
        Returns:
            Recognized text or None if timeout.
        """
        try:
            return self.text_queue.get(timeout=timeout)
        except queue.Empty:
            return None
