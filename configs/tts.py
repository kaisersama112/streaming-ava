"""TTS configuration schemas."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class DoubaoTTSAudioParams(BaseModel):
    """Doubao TTS req_params.audio_params."""

    format: str = Field(default="mp3", description="音频编码格式，可选 mp3 / ogg_opus / pcm")
    sample_rate: int = Field(default=24000, description="音频采样率，可选 8000/16000/22050/24000/32000/44100/48000")
    bit_rate: Optional[int] = Field(default=None, description="音频比特率，仅对 MP3 格式有效")
    emotion: Optional[str] = Field(default=None, description="音色情感，例如 angry / happy / neutral")
    emotion_scale: Optional[float] = Field(default=4, description="情绪强度，范围 1~5")
    speech_rate: int = Field(default=0, description="语速，取值范围 [-50, 100]")
    loudness_rate: int = Field(default=0, description="音量，取值范围 [-50, 100]")
    enable_timestamp: bool = Field(default=False, description="是否开启时间戳，仅 TTS 1.0 支持")
    enable_subtitle: bool = Field(default=False, description="是否开启字幕，仅 TTS 2.0 / ICL 2.0 生效")


class DoubaoTTSAIGCMetadata(BaseModel):
    enable: bool = Field(default=False, description="是否启用隐式水印")
    content_producer: str = Field(default="", description="内容制作服务提供者")
    produce_id: str = Field(default="", description="内容制作编号")
    content_propagator: str = Field(default="", description="内容传播服务提供者")
    propagate_id: str = Field(default="", description="内容传播编号")


class DoubaoTTSCacheConfig(BaseModel):
    text_type: int = Field(default=1, description="开启缓存时传 1")
    use_cache: bool = Field(default=True, description="是否使用缓存")


class DoubaoTTSPostProcess(BaseModel):
    pitch: int = Field(default=0, description="音调，取值范围 [-12, 12]")


class DoubaoTTSAdditions(BaseModel):
    """Doubao TTS req_params.additions."""

    silence_duration: int = Field(default=0, description="句尾静音时长，范围 0~30000ms")
    enable_language_detector: bool = Field(default=False, description="是否自动识别语种")
    disable_markdown_filter: bool = Field(default=False, description="是否开启 Markdown 解析过滤")
    disable_emoji_filter: bool = Field(default=False, description="是否不过滤 emoji")
    mute_cut_threshold: Optional[str] = Field(default=None, description="静音判断阈值，需配合 mute_cut_remain_ms 使用")
    mute_cut_remain_ms: Optional[str] = Field(default=None, description="保留静音长度，需配合 mute_cut_threshold 使用")
    enable_latex_tn: bool = Field(default=False, description="是否可以播报 LaTeX 公式")
    latex_parser: Union[bool, str] = Field(default=False, description="LaTeX 解析能力，可为 true / false / v2")
    max_length_to_filter_parenthesis: int = Field(default=100, description="过滤括号内容阈值，0 为不过滤")
    explicit_language: Optional[str] = Field(default=None, description="明确语种，例如 zh-cn / en / ja")
    context_language: Optional[str] = Field(default=None, description="参考语种，例如 id / es / pt")
    explicit_dialect: Optional[str] = Field(default=None, description="明确方言，例如 dongbei / shaanxi / sichuan")
    unsupported_char_ratio_thresh: float = Field(default=0.3, description="不支持字符比例阈值，最大 1.0")
    aigc_watermark: bool = Field(default=False, description="是否在合成结尾增加音频节奏标识")
    aigc_metadata: Optional[DoubaoTTSAIGCMetadata] = Field(default=None, description="隐式水印 header 元数据")
    cache_config: Optional[DoubaoTTSCacheConfig] = Field(default=None, description="缓存配置")
    post_process: Optional[DoubaoTTSPostProcess] = Field(default=None, description="后处理配置")
    context_texts: Optional[List[str]] = Field(default=None, description="语音合成辅助信息，仅 TTS 2.0 支持")
    use_tag_parser: bool = Field(default=False, description="是否开启 cot 解析能力")


class DoubaoTTSReqParams(BaseModel):
    """Doubao TTS request body req_params."""

    text: Optional[str] = Field(default=None, description="TTS 输入文本；text 和 ssml 至少一个不为空")
    ssml: Optional[str] = Field(default=None, description="SSML 文本；优先级高于 text")
    model: Optional[str] = Field(default=None, description="模型版本，例如 seed-tts-2.0-standard")
    speaker: str = Field(..., description="发音人 ID，例如 saturn_zh_male_shuanglangshaonian_tob")
    audio_params: DoubaoTTSAudioParams = Field(default_factory=DoubaoTTSAudioParams, description="音频参数")
    additions: Optional[DoubaoTTSAdditions] = Field(default=None, description="用户自定义参数")
    mix_speaker: Optional[Dict[str, Any]] = Field(default=None, description="混音参数，仅适用于 TTS 1.0 音色")


class Cosyvoice(BaseModel):
    api_base: str = Field(
        "https://dashscope.aliyuncs.com/api/v1/services/audio/tts/SpeechSynthesizer",
        description="TTS 接口地址",
    )
    api_key: str = Field("", description="TTS 接口密钥")
    model: str = Field("cosyvoice-v3-flash", description="TTS 模型名称")
    voice: str = Field("longanyang", description="发音人")
    instruction: str = Field("", description="语音指令")


class StepFun(BaseModel):
    api_key: str = Field("", description="StepFun TTS API Key")
    ws_url: str = Field("wss://api.stepfun.com/v1/realtime/audio", description="StepFun TTS WebSocket 地址")
    model: str = Field("stepaudio-2.5-tts", description="StepFun TTS 模型名称")
    voice: str = Field("cixingnansheng", description="StepFun TTS 音色")
    instruction: str = Field("", description="StepFun TTS 语音指令")


class DouBao(BaseModel):
    x_api_key: str = Field("", description="豆包语音 X-Api-Key")
    x_api_resource_id: str = Field("seed-tts-2.0", description="豆包语音 X-Api-Resource-Id")
    model: str = Field("seed-tts-2.0", description="豆包语音模型 / Resource ID")
    req_params: DoubaoTTSReqParams = Field(
        default_factory=lambda: DoubaoTTSReqParams(speaker=""),
        description="豆包语音请求体 req_params 配置",
    )
    ws_url: str = Field("wss://openspeech.bytedance.com/api/v3/tts/bidirection", description="豆包语音双向 WebSocket 地址")
    sse_url: str = Field("https://openspeech.bytedance.com/api/v3/tts/unidirectional/sse", description="豆包语音单向 SSE 地址")


class VoiceConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    provider: str = Field("cosyvoice", description="TTS provider: cosyvoice / stepfun / doubao")
    cosyvoice: Cosyvoice = Field(default_factory=Cosyvoice, description="TTS cosyvoice")
    step_fun: StepFun = Field(default_factory=StepFun, description="TTS stepfun")
    dou_bao: DouBao = Field(
        default_factory=DouBao,
        validation_alias=AliasChoices("dou_bao", "doubao"),
        description="TTS DouBao",
    )
    volume: int = Field(50, description="音量调节")
    speech_rate: float = Field(1.0, description="语速调节")
    pitch_rate: float = Field(1.0, description="语调调节")
    format: str = Field("wav", description="音频格式")
    sample_rate: int = Field(24000, description="音频采样率")
    timeout: int = Field(120, description="TTS 超时时间（秒）")
