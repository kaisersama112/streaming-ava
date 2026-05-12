"""Convenience helpers for one-shot ASR over recorded audio blobs."""

from __future__ import annotations

import io
import time
import wave

from .asr_streaming_client import StreamingASRClient
from .asr_streaming_sdk import ASRConfig


def _extract_pcm(audio_data: bytes, fmt: str, sample_rate: int) -> tuple[bytes, int]:
    if fmt.lower() == "wav":
        with wave.open(io.BytesIO(audio_data), "rb") as wav_file:
            frames = wav_file.readframes(wav_file.getnframes())
            return frames, int(wav_file.getframerate() or sample_rate)
    return audio_data, sample_rate


def recognize_text(
    *,
    audio_data: bytes,
    api_key: str,
    model: str,
    format: str = "wav",
    sample_rate: int = 16000,
    language: str = "zh",
    websocket_url: str = "wss://dashscope.aliyuncs.com/api-ws/v1/realtime",
    timeout: float = 15.0,
) -> str:
    pcm_bytes, resolved_rate = _extract_pcm(audio_data, format, sample_rate)
    cfg = ASRConfig(
        api_key=api_key,
        model=model,
        language=language,
        sample_rate=resolved_rate,
        input_audio_format="pcm",
        websocket_url=websocket_url,
    )
    client = StreamingASRClient(cfg)
    partial_text = ""
    final_text = ""
    try:
        client.start()
        for offset in range(0, len(pcm_bytes), 3200):
            client.send_audio(pcm_bytes[offset : offset + 3200])
            time.sleep(0.01)

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            results = client.pop_results(max_items=32)
            if not results:
                time.sleep(0.05)
                continue
            for result in results:
                if result.text.strip():
                    partial_text = result.text.strip()
                if result.is_final and result.text.strip():
                    final_text = result.text.strip()
            if final_text:
                break
        return final_text or partial_text
    finally:
        client.stop()
