"""
Doubao / Volcengine realtime ASR provider configuration.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class DoubaoASRAudio(BaseModel):
    """Doubao ASR full client request audio section."""

    format: str = Field("pcm", description="Audio container format: pcm / wav / ogg / mp3")
    codec: str = Field("raw", description="Audio codec: raw / opus")
    rate: int = Field(16000, description="Audio sample rate; BigASR currently expects 16000")
    bits: int = Field(16, description="PCM bit depth")
    channel: int = Field(1, description="Audio channels")
    language: str = Field("zh-CN", description="Recognition language, for supported modes")


class DoubaoASRRequest(BaseModel):
    """Doubao ASR full client request request section."""

    model_name: str = Field("bigmodel", description="Doubao ASR model name")
    enable_itn: bool = Field(True, description="Enable inverse text normalization")
    enable_punc: bool = Field(True, description="Enable punctuation")
    enable_ddc: bool = Field(False, description="Enable DDC")
    show_utterances: bool = Field(True, description="Return utterance details")
    enable_nonstream: bool = Field(False, description="Enable non-stream second-pass result")
    enable_emotion_detection: bool = Field(False, description="Enable emotion detection")
    end_window_size: Optional[int] = Field(default=None, description="VAD end window size in ms")
    corpus: Optional[Dict[str, Any]] = Field(default=None, description="Hotword/context corpus config")
    extra: Dict[str, Any] = Field(default_factory=dict, description="Extra request fields")


class DoubaoASR(BaseModel):
    """Doubao ASR WebSocket credentials and request settings."""

    model_config = ConfigDict(populate_by_name=True)

    x_api_key: str = Field(
        "",
        validation_alias=AliasChoices("x_api_key", "api_key", "app_key"),
        description="Volcengine X-Api-Key",
    )
    x_api_resource_id: str = Field(
        "volc.seedasr.sauc.duration",
        validation_alias=AliasChoices("x_api_resource_id", "resource_id"),
        description="豆包流式语音识别模型1.0"
                    "小时版：volc.bigasr.sauc.duration"
                    "并发版：volc.bigasr.sauc.concurrent"
                    "豆包流式语音识别模型2.0"
                    "小时版：volc.seedasr.sauc.duration"
                    "并发版：volc.seedasr.sauc.concurrent",
    )
    x_api_request_id: str = Field(
        "",
        validation_alias=AliasChoices("x_api_request_id", "request_id"),
        description="Volcengine X-Api-Request-Id；留空时每次连接自动生成 UUID",
    )
    ws_url: str = Field(
        "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async",
        description="Doubao BigModel streaming ASR WebSocket URL",
    )
    uid: str = Field("streaming_ava", description="User identifier for ASR logs")
    audio: DoubaoASRAudio = Field(default_factory=DoubaoASRAudio, description="Audio metadata")
    request: DoubaoASRRequest = Field(default_factory=DoubaoASRRequest, description="Request parameters")
    websocket_connect_timeout_sec: float = Field(10.0, description="WebSocket connect timeout")
    websocket_ping_interval_sec: float = Field(15.0, description="WebSocket ping interval")
    websocket_ping_timeout_sec: float = Field(8.0, description="WebSocket ping timeout")
