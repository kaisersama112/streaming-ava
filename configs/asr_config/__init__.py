"""
ASR provider configuration facade.
"""

from __future__ import annotations

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from .doubao import DoubaoASR
from .qwen import Qwen3ASR


class ASRConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    provider: str = Field("qwen3_asr", description="ASR provider: qwen3_asr / dou_bao")
    qwen3_asr: Qwen3ASR = Field(
        default_factory=Qwen3ASR,
        validation_alias=AliasChoices("qwen3_asr", "qwen_asr", "qwen"),
        description="Qwen3 ASR realtime provider config",
    )
    dou_bao: DoubaoASR = Field(
        default_factory=DoubaoASR,
        validation_alias=AliasChoices("dou_bao", "doubao", "doubao_asr"),
        description="Doubao ASR provider config",
    )

    # Backward-compatible flat fields. Existing configs can keep using the old
    # shape while new configs can use provider-specific sections, like TTS.
    api_key: str = Field("", description="Legacy Qwen ASR API Key")
    model: str = Field("qwen3-asr-flash-realtime", description="Legacy Qwen ASR model")
    format: str = Field("pcm", description="Legacy input audio format")
    sample_rate: int = Field(16000, description="Legacy input sample rate")
    language: str = Field("zh", description="Legacy language code")
    websocket_url: str = Field(
        "wss://dashscope.aliyuncs.com/api-ws/v1/realtime",
        description="Legacy Qwen ASR WebSocket URL",
    )
    websocket_connect_timeout_sec: float = Field(10.0, description="Legacy WebSocket connect timeout")
    websocket_ping_interval_sec: float = Field(15.0, description="Legacy WebSocket ping interval")
    websocket_ping_timeout_sec: float = Field(8.0, description="Legacy WebSocket ping timeout")
    enable_turn_detection: bool = Field(True, description="Legacy server VAD switch")
    turn_detection_threshold: float = Field(0.45, description="Legacy server VAD threshold")
    turn_detection_silence_duration_ms: int = Field(850, description="Legacy server VAD silence duration")


__all__ = ["ASRConfig", "DoubaoASR", "Qwen3ASR"]
