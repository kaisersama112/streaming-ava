from pathlib import Path
from typing import Optional
import os

import yaml
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent.parent


class ServerConfig(BaseModel):
    title: str = Field("streaming-ava", description="服务标题")
    host: str = Field("0.0.0.0", description="服务监听地址")
    port: int = Field(7000, description="服务端口")
    reload: bool = Field(False, description="是否自动热重载")
    workers: int = Field(1, description="工作进程数量")


class OpenAIConfig(BaseModel):
    api_base: str = Field(
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
        description="兼容 OpenAI 的基础 URL",
    )
    api_key: str = Field("", description="LLM 接口密钥")
    model: str = Field("qwen-plus", description="LLM 模型名称")
    multimodal_model: str = Field("qwen3.5-omni-plus", description="多模态 LLM 模型名称")
    intent_model: str = Field("tongyi-intent-detect-v3", description="意图理解模型名称")
    timeout: int = Field(60, description="LLM 超时时间（秒）")
    intent_timeout: int = Field(8, description="意图理解模型超时时间（秒）")


class VoiceConfig(BaseModel):
    api_base: str = Field(
        "https://dashscope.aliyuncs.com/api/v1/services/audio/tts/SpeechSynthesizer",
        description="TTS 接口地址",
    )
    api_key: str = Field("", description="TTS 接口密钥")
    model: str = Field("cosyvoice-v3-flash", description="TTS 模型名称")
    voice: str = Field("longanyang", description="发音人")
    volume: int = Field(50, description="音量调节")
    speech_rate: float = Field(1.0, description="语速调节")
    pitch_rate: float = Field(1.0, description="语调（音高）调节")
    instruction: str = Field("", description="该功能适用于音色列表中已标记支持 Instruct 的系统音色")
    format: str = Field("wav", description="音频格式")
    sample_rate: int = Field(24000, description="音频采样率")
    timeout: int = Field(120, description="TTS 超时时间（秒）")


class ASRConfig(BaseModel):
    api_key: str = Field("", description="ASR 接口密钥")
    model: str = Field("qwen3-asr-flash-realtime", description="ASR 模型名称")
    format: str = Field("pcm", description="音频格式")
    sample_rate: int = Field(16000, description="音频采样率")
    language: str = Field("zh", description="语言代码")
    websocket_url: str = Field("wss://dashscope.aliyuncs.com/api-ws/v1/realtime", description="ASR WebSocket 地址")
    websocket_ping_interval_sec: float = Field(15.0, description="ASR WebSocket Ping 间隔（秒）")
    websocket_ping_timeout_sec: float = Field(8.0, description="ASR WebSocket Ping 超时（秒）")
    enable_turn_detection: bool = Field(True, description="是否启用服务端回合检测")
    turn_detection_threshold: float = Field(0.45, description="服务端 VAD 阈值")
    turn_detection_silence_duration_ms: int = Field(850, description="静音多长时间后判定结束（毫秒）")


class RuntimeConfig(BaseModel):
    """运行时行为配置。

    涵盖会话状态、日志追踪、实时音频推流、Barge-in 打断检测
    以及回声过滤等子系统的可调参数。所有字段均可通过
    ``config/config.yaml`` 的 ``runtime`` 块覆盖默认值。
    """

    state_file: str = Field("state/memory.json", description="会话状态文件路径")
    default_session_id: str = Field("default", description="默认会话 ID")
    evaluation_log_file: str = Field("state/evaluation.jsonl", description="策略评估日志文件路径")
    trace_log_file: str = Field("state/trace.jsonl", description="结构化追踪日志文件路径")
    trace_log_enabled: bool = Field(True, description="是否启用结构化逐步追踪日志")
    trace_log_asr_partials: bool = Field(True, description="是否在追踪日志中记录 ASR partial 事件")
    trace_max_text_chars: int = Field(12000, description="追踪文本字段保留的最大字符数")
    history_window: int = Field(8, description="历史轮次窗口大小")
    max_context_messages: int = Field(16, description="发送给模型的用户/助手历史消息最大数量")
    output_dir: str = Field("outputs", description="音频输出目录")
    realtime_audio_host: str = Field("0.0.0.0", description="FastRTC 播放器监听地址")
    realtime_audio_port: int = Field(7860, description="FastRTC 播放器端口")
    realtime_audio_public_url: str = Field("", description="FastRTC 对外访问地址")
    prompt_dir: str = Field("prompt-plugin", description="提示词中心目录")
    router_model: str = Field("", description="路由模型名称，默认跟随 openai_config.model")
    router_timeout: int = Field(30, description="路由模型超时时间（秒）")
    agents_sdk_enabled: bool = Field(False, description="是否启用 OpenAI Agents SDK 作为执行层")
    agents_sdk_realtime_enabled: bool = Field(False, description="是否在 realtime 主链启用 Agents SDK 流式执行")
    agents_sdk_tracing_enabled: bool = Field(False, description="是否启用 Agents SDK tracing")
    agents_sdk_timeout: int = Field(45, description="Agents SDK 执行超时时间（秒）")
    agents_sdk_max_turns: int = Field(6, description="Agents SDK 单次运行允许的最大内部轮次")
    agents_sdk_model: str = Field("", description="Agents SDK 文本模型名称，默认跟随 openai_config.model")
    agents_sdk_multimodal_model: str = Field("", description="Agents SDK 多模态模型名称，默认跟随 openai_config.multimodal_model")
    agents_sdk_session_db: str = Field("state/agents_sessions.json", description="Agents SDK 会话存储路径")
    agents_sdk_branches: list[str] = Field(
        default_factory=lambda: ["education", "general_qa", "clarify"],
        description="允许切换到 Agents SDK 执行层的 branch 列表",
    )
    agents_sdk_education_modules: list[str] = Field(
        default_factory=lambda: ["solve", "check", "explain", "answer", "qa"],
        description="教育分支允许切换到 Agents SDK 执行层的 module 列表",
    )
    debug_audio_dump: bool = Field(False, description="是否启用调试音频转储")
    realtime_audio_frame_ms: int = Field(60, description="PCM 推流分帧时长（毫秒）")
    realtime_audio_max_lead_seconds: float = Field(0.05, description="音频播放允许超前的最大秒数")
    realtime_tts_close_timeout_seconds: float = Field(45.0, description="流结束后等待 TTS feeder 关闭的最长时间（秒）")
    realtime_audio_pump_drain_timeout_seconds: float = Field(45.0, description="TTS 关闭后等待音频泵排空的最长时间（秒）")
    realtime_audio_rebuild_on_interrupt: bool = Field(True, description="被打断后是否重建播放流")

    # --- Barge-in 打断检测参数 ---
    # 控制用户说话时是否触发对当前 TTS 播放的打断。
    barge_in_partial_chars: int = Field(2, description="触发打断所需的 ASR partial 最小字符数")
    barge_in_stability_threshold: float = Field(0.35, description="触发打断所需的 partial 最小稳定度")
    barge_in_cooldown_ms: int = Field(450, description="两次打断之间的最小间隔（毫秒）")

    # --- 回声检测参数 ---
    # TTS 播放时，麦克风会拾取扬声器声音，ASR 会将其识别为 partial。
    # 以下参数用于区分“TTS 回声”和“用户真实输入”，避免 AVA 自己打断自己。
    # 详见 RealtimeSession._looks_like_playback_echo() 的实现说明。
    echo_detection_window_seconds: float = Field(
        0.5,
        description=(
            "TTS 最后一帧推出后的时间窗口（秒）。"
            "仅窗口内的 ASR partial 会进行回声检测；超出窗口则直接视为真实用户输入。"
        ),
    )
    echo_detection_min_chars: int = Field(
        4,
        description=(
            "触发回声检测所需的 ASR partial 最小字符数（去除空白后）。"
            "过短文本（如“嗯”“好”）无法可靠比对，低于此值将直接放行。"
        ),
    )
    echo_detection_similarity_threshold: float = Field(
        0.85,
        description=(
            "SequenceMatcher 模糊相似度阈值（0~1）。"
            "当 ASR partial 与 assistant 文本尾部的相似度达到该值时，判定为回声并过滤。"
            "值越高越保守（误判少但漏判多），值越低越激进（过滤更多但可能误伤真实输入）。"
        ),
    )


class SpeechPostprocessConfig(BaseModel):
    enabled: bool = Field(True, description="是否启用 TTS 前语音后处理")
    math_oralizer_enabled: bool = Field(True, description="是否启用数学 LaTeX 口语化")
    latex_span_only: bool = Field(True, description="是否只替换 LaTeX 片段并保留其他文本不变")
    math_stream_buffer_enabled: bool = Field(True, description="是否在实时数学场景启用 LaTeX 感知流缓冲")
    stream_flush_chars: int = Field(72, description="安全缓冲字符数超过该阈值时强制刷新")


class Config(BaseModel):
    server: ServerConfig = Field(default_factory=ServerConfig)
    openai_config: OpenAIConfig = Field(default_factory=OpenAIConfig)
    voice_config: VoiceConfig = Field(default_factory=VoiceConfig)
    asr_config: ASRConfig = Field(default_factory=ASRConfig)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    speech_postprocess: SpeechPostprocessConfig = Field(default_factory=SpeechPostprocessConfig)


def load_config(config_path: Optional[Path] = None) -> Config:
    path = config_path or (BASE_DIR / "config" / "config.yaml")
    if not path.exists():
        cfg = Config()
        _apply_env_overrides(cfg)
        return cfg
    with open(path, "r", encoding="utf-8") as f:
        raw_config = yaml.safe_load(f) or {}
    cfg = Config.model_validate(raw_config)
    _apply_env_overrides(cfg)
    return cfg


def _apply_env_overrides(cfg: Config) -> None:
    """当敏感字段为空时，从环境变量补全。

    可以避免在 `config/config.yaml` 中明文保存密钥。
    """
    cfg.openai_config.api_key = cfg.openai_config.api_key or os.getenv("STREAMING_AVA_OPENAI_API_KEY", "")
    cfg.voice_config.api_key = cfg.voice_config.api_key or os.getenv("STREAMING_AVA_TTS_API_KEY", "")
    cfg.asr_config.api_key = cfg.asr_config.api_key or os.getenv("STREAMING_AVA_ASR_API_KEY", "")


settings = load_config()
