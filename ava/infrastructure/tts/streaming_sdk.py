"""DashScope CosyVoice streaming SDK adapter."""

from __future__ import annotations

import queue
import threading


class CosyVoiceSDKError(RuntimeError):
    pass


def _resolve_audio_format(fmt: str, sample_rate: int):
    from dashscope.audio.tts_v2 import AudioFormat

    fmt = fmt.lower()
    mapping = {
        ("wav", 24000): AudioFormat.WAV_24000HZ_MONO_16BIT,
        ("wav", 22050): AudioFormat.WAV_22050HZ_MONO_16BIT,
        ("wav", 16000): AudioFormat.WAV_16000HZ_MONO_16BIT,
        ("mp3", 24000): AudioFormat.MP3_24000HZ_MONO_256KBPS,
        ("mp3", 22050): AudioFormat.MP3_22050HZ_MONO_256KBPS,
        ("mp3", 16000): AudioFormat.MP3_16000HZ_MONO_128KBPS,
        ("pcm", 24000): AudioFormat.PCM_24000HZ_MONO_16BIT,
        ("pcm", 22050): AudioFormat.PCM_22050HZ_MONO_16BIT,
        ("pcm", 16000): AudioFormat.PCM_16000HZ_MONO_16BIT,
    }
    return mapping.get((fmt, sample_rate), AudioFormat.WAV_24000HZ_MONO_16BIT)


class _ChunkCallback:  # duck-typed callback for dashscope
    def __init__(self):
        self.chunks: queue.Queue[bytes] = queue.Queue()
        self.done = threading.Event()
        self.error: str | None = None

    def on_open(self):
        return None

    def on_complete(self):
        self.done.set()

    def on_close(self):
        self.done.set()

    def on_data(self, data):
        if data:
            self.chunks.put(bytes(data))

    def on_error(self, message):
        self.error = str(message)
        self.done.set()

    def on_event(self, message):
        return None


class StreamingCosyVoice:
    """Thin wrapper around DashScope streaming TTS with normalized errors."""

    def __init__(
            self,
            api_key: str,
            model: str = "cosyvoice-v3-flash",
            voice: str = "longxiaoxia_v3",
            volume: int = 50,
            speech_rate: float = 1.0,
            pitch_rate: float = 1.0,
            instruction: str = None,
            audio_format: str = "wav",
            sample_rate: int = 24000,
    ):
        try:
            import dashscope
            from dashscope.audio.tts_v2 import SpeechSynthesizer
        except ImportError as exc:  # pragma: no cover
            raise CosyVoiceSDKError(
                "dashscope SDK not installed. Run: pip install dashscope>=1.24.5"
            ) from exc

        if not api_key:
            raise CosyVoiceSDKError("CosyVoice api_key is empty.")

        dashscope.api_key = api_key
        self.callback = _ChunkCallback()
        af = _resolve_audio_format(audio_format, sample_rate)
        self.synth = SpeechSynthesizer(
            model=model,
            voice=voice,
            volume=volume,
            speech_rate=speech_rate,
            pitch_rate=pitch_rate,
            instruction=instruction,
            format=af,
            callback=self.callback,
        )
        self._is_completed = False

    def feed(self, text: str) -> None:
        content = text.strip()
        if content and not self._is_completed:
            retry_count = 0
            max_retries = 3
            while retry_count < max_retries:
                try:
                    self.synth.streaming_call(content)
                    return
                except Exception as exc:
                    retry_count += 1
                    if retry_count >= max_retries:
                        raise CosyVoiceSDKError(f"streaming_call failed: {exc}") from exc
                    # 短暂延迟后重试
                    import time
                    time.sleep(0.1)

    def complete(self, timeout_millis: int = 120000) -> None:
        if self._is_completed:
            return
        try:
            self.synth.streaming_complete(timeout_millis)
            self._is_completed = True
        except Exception as exc:
            raise CosyVoiceSDKError(f"streaming_complete failed: {exc}") from exc

    def pop_chunks(self) -> list[bytes]:
        out: list[bytes] = []
        try:
            while True:
                try:
                    chunk = self.callback.chunks.get_nowait()
                    if chunk:
                        out.append(chunk)
                except queue.Empty:
                    break
                except Exception:
                    # 忽略获取单个音频块时的异常
                    continue
        except Exception:
            # 忽略获取音频块时的异常
            pass
        return out


def synthesize_text(
        text: str,
        api_key: str,
        model: str = "cosyvoice-v3-flash",
        voice: str = "longxiaoxia_v3",
        volume: int = 50,
        speech_rate: float = 1.0,
        pitch_rate: float = 1.0,
        instruction: str = None,
        audio_format: str = "wav",
        sample_rate: int = 24000,
) -> bytes:
    tts = StreamingCosyVoice(
        api_key=api_key,
        model=model,
        voice=voice,
        volume=volume,
        speech_rate=speech_rate,
        pitch_rate=pitch_rate,
        instruction=instruction,
        audio_format=audio_format,
        sample_rate=sample_rate,
    )
    tts.feed(text)
    tts.complete()
    return b"".join(tts.pop_chunks())
