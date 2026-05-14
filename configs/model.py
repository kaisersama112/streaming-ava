"""Model and provider configuration schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field

from configs.tts import VoiceConfig


class OpenAIConfig(BaseModel):
    api_base: str = Field("https://dashscope.aliyuncs.com/compatible-mode/v1", description="兼容 OpenAI 的基础 URL")
    api_key: str = Field("", description="LLM 接口密钥")
    model: str = Field("qwen-plus", description="LLM 模型名称")
    multimodal_model: str = Field("qwen3.5-omni-plus", description="多模态 LLM 模型名称")
    intent_model: str = Field("tongyi-intent-detect-v3", description="意图理解模型名称")
    timeout: int = Field(60, description="LLM 超时时间（秒）")
    intent_timeout: int = Field(8, description="意图理解模型超时时间（秒）")


class BigModelConfig(BaseModel):
    api_base: str = Field("https://open.bigmodel.cn/api/paas/v4", description="智谱兼容接口地址")
    api_key: str = Field("", description="智谱 API Key")
    model: str = Field("glm-4.6v-flash", description="智谱模型名称")
    timeout: int = Field(15, description="智谱请求超时时间（秒）")
    enabled: bool = Field(False, description="是否启用智谱模型配置")


class ASRConfig(BaseModel):
    api_key: str = Field("", description="ASR 接口密钥")
    model: str = Field("qwen3-asr-flash-realtime", description="ASR 模型名称")
    format: str = Field("pcm", description="音频格式")
    sample_rate: int = Field(16000, description="音频采样率")
    language: str = Field("zh", description="语言代码")
    websocket_url: str = Field("wss://dashscope.aliyuncs.com/api-ws/v1/realtime", description="ASR WebSocket 地址")
    websocket_connect_timeout_sec: float = Field(10.0, description="ASR WebSocket 建连超时（秒）")
    websocket_ping_interval_sec: float = Field(15.0, description="ASR WebSocket Ping 间隔（秒）")
    websocket_ping_timeout_sec: float = Field(8.0, description="ASR WebSocket Ping 超时（秒）")
    enable_turn_detection: bool = Field(True, description="是否启用服务端回合检测")
    turn_detection_threshold: float = Field(0.45, description="服务端 VAD 阈值")
    turn_detection_silence_duration_ms: int = Field(850, description="静音多长时间后判定结束（毫秒）")
