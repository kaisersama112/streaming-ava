"""
Qwen realtime ASR provider configuration.
"""

from __future__ import annotations

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class Qwen3ASR(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    api_key: str = Field("", description="DashScope ASR API Key")
    model: str = Field("qwen3-asr-flash-realtime", description="Qwen ASR realtime model")
    input_audio_format: str = Field(
        "pcm",
        validation_alias=AliasChoices("input_audio_format", "format"),
        description="Input audio format",
    )
    sample_rate: int = Field(16000, description="Input audio sample rate")
    language: str = Field("zh", description="Language code")
    websocket_url: str = Field(
        "wss://dashscope.aliyuncs.com/api-ws/v1/realtime",
        description="DashScope realtime WebSocket URL",
    )
    websocket_connect_timeout_sec: float = Field(10.0, description="WebSocket connect timeout")
    websocket_ping_interval_sec: float = Field(15.0, description="WebSocket ping interval")
    websocket_ping_timeout_sec: float = Field(8.0, description="WebSocket ping timeout")
    enable_turn_detection: bool = Field(True, description="Enable server-side turn detection")
    turn_detection_threshold: float = Field(0.45, description="Server VAD threshold")
    turn_detection_silence_duration_ms: int = Field(850, description="Server VAD silence duration")
