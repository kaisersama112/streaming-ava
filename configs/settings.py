from pathlib import Path
from typing import Any, Optional
import os
import yaml
from pydantic import BaseModel, Field

from .llm_config import BigModelConfig, OpenAIConfig
from .asr_config import ASRConfig
from .tts_config import VoiceConfig

BASE_DIR = Path(__file__).resolve().parent.parent


class ServerConfig(BaseModel):
    title: str = Field("streaming-ava", description="服务标题")
    host: str = Field("0.0.0.0", description="服务监听地址")
    port: int = Field(7000, description="服务端口")
    reload: bool = Field(False, description="是否自动热重载")
    workers: int = Field(1, description="工作进程数量")


class SpeechPostprocessConfig(BaseModel):
    enabled: bool = Field(True, description="是否启用 TTS 前语音后处理")
    math_oralizer_enabled: bool = Field(True, description="是否启用数学 LaTeX 口语化")
    latex_span_only: bool = Field(True, description="是否只替换 LaTeX 片段")
    math_stream_buffer_enabled: bool = Field(True, description="是否启用 LaTeX 感知流缓冲")
    stream_flush_chars: int = Field(72, description="安全缓冲字符数阈值")


class RuntimeConfig(BaseModel):
    state_file: str = Field("state/memory.json", description="会话状态文件路径")
    default_session_id: str = Field("default", description="默认会话 ID")
    evaluation_log_file: str = Field("state/evaluation.jsonl", description="策略评估日志文件路径")
    history_window: int = Field(8, description="历史轮次窗口大小")
    max_context_messages: int = Field(16, description="发送给模型的历史消息最大数量")
    router_max_context_messages: int = Field(8, description="Router 最大上下文消息数")
    responder_max_context_messages: int = Field(16, description="Responder 最大上下文消息数")
    output_dir: str = Field("outputs", description="音频输出目录")
    realtime_audio_host: str = Field("0.0.0.0", description="FastRTC 播放器监听地址")
    realtime_audio_port: int = Field(7860, description="FastRTC 播放器端口")
    realtime_audio_public_url: str = Field("", description="FastRTC 对外访问地址")
    prompt_dir: str = Field("prompt-plugin", description="提示词中心目录")
    router_model: str = Field("", description="路由模型名称")
    router_timeout: int = Field(30, description="路由模型超时时间（秒）")
    agents_sdk_enabled: bool = Field(False, description="是否启用 OpenAI Agents SDK")
    agents_sdk_realtime_enabled: bool = Field(False, description="是否在 realtime 主链启用 Agents SDK")
    agents_sdk_timeout: int = Field(45, description="Agents SDK 执行超时时间（秒）")
    agents_sdk_max_turns: int = Field(6, description="Agents SDK 单次运行最大内部轮次")
    agents_sdk_model: str = Field("", description="Agents SDK 文本模型名称")
    agents_sdk_multimodal_model: str = Field("", description="Agents SDK 多模态模型名称")
    agents_sdk_session_db: str = Field("state/agents_sessions.json", description="Agents SDK 会话存储路径")
    agents_sdk_branches: list[str] = Field(
        default_factory=lambda: ["education", "general_qa", "clarify"],
        description="允许切换到 Agents SDK 的 branch 列表",
    )
    agents_sdk_education_modules: list[str] = Field(
        default_factory=lambda: ["solve", "check", "explain", "answer", "qa"],
        description="允许切换到 Agents SDK 的教学 module 列表",
    )
    debug_audio_dump: bool = Field(False, description="是否启用调试音频转储")
    realtime_audio_frame_ms: int = Field(60, description="PCM 推流分帧时长（毫秒）")
    realtime_audio_max_lead_seconds: float = Field(0.05, description="音频播放允许超前的最大秒数")
    realtime_tts_complete_timeout_millis: int = Field(45000, description="流式 TTS complete 等待超时（毫秒）")
    realtime_tts_done_drain_grace_seconds: float = Field(2.0,
                                                         description="TTS done 后继续等待尾部音频到达的宽限时间（秒）")
    realtime_tts_close_timeout_seconds: float = Field(45.0, description="流结束后等待 TTS feeder 关闭的最长时间")
    realtime_audio_pump_drain_timeout_seconds: float = Field(45.0, description="TTS 关闭后等待音频泵排空的最长时间")
    realtime_audio_rebuild_on_interrupt: bool = Field(True, description="被打断后是否重建播放流")
    barge_in_partial_chars: int = Field(2, description="触发打断所需的 ASR partial 最小字符数")
    barge_in_stability_threshold: float = Field(0.35, description="触发打断所需的 partial 最小稳定度")
    barge_in_cooldown_ms: int = Field(450, description="两次打断之间的最小间隔（毫秒）")
    echo_detection_window_seconds: float = Field(0.5, description="TTS 最后一帧推出后的时间窗口（秒）")
    echo_detection_min_chars: int = Field(4, description="触发回声检测所需的 ASR partial 最小字符数")
    echo_detection_similarity_threshold: float = Field(0.85, description="回声检测相似度阈值")


class Config(BaseModel):
    config_files: list[str] = Field(default_factory=list, description="额外配置文件，按顺序加载后由主配置覆盖")
    server: ServerConfig = Field(default_factory=ServerConfig)
    openai_config: OpenAIConfig = Field(default_factory=OpenAIConfig)
    bigmodel_config: BigModelConfig = Field(default_factory=BigModelConfig)
    voice_config: VoiceConfig = Field(default_factory=VoiceConfig)
    asr_config: ASRConfig = Field(default_factory=ASRConfig)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    speech_postprocess: SpeechPostprocessConfig = Field(default_factory=SpeechPostprocessConfig)


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data if isinstance(data, dict) else {}


def _resolve_config_path(value: str, *, base_path: Path) -> Path:
    raw = Path(str(value or "").strip())
    if raw.is_absolute():
        return raw
    from_project_root = BASE_DIR / raw
    if from_project_root.exists():
        return from_project_root
    return base_path.parent / raw


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base or {})
    for key, value in dict(override or {}).items():
        if isinstance(merged.get(key), dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _load_with_includes(path: Path, *, seen: set[Path] | None = None) -> dict[str, Any]:
    resolved = path.resolve()
    seen = seen or set()
    if resolved in seen:
        return {}
    seen.add(resolved)

    raw_config = _read_yaml(resolved)
    includes = raw_config.get("config_files") or []
    if isinstance(includes, str):
        includes = [includes]

    merged: dict[str, Any] = {}
    for include in includes:
        include_path = _resolve_config_path(str(include), base_path=resolved)
        merged = _deep_merge(merged, _load_with_includes(include_path, seen=seen))

    return _deep_merge(merged, raw_config)


def load_config(config_path: Optional[Path] = None) -> Config:
    path = config_path or (BASE_DIR / "configs" / "config.yaml")
    if not path.exists():
        cfg = Config()
        _apply_env_overrides(cfg)
        return cfg
    cfg = Config.model_validate(_load_with_includes(path))
    _apply_env_overrides(cfg)
    return cfg


def _apply_env_overrides(cfg: Config) -> None:
    cfg.openai_config.api_key = cfg.openai_config.api_key or os.getenv("STREAMING_AVA_OPENAI_API_KEY", "")
    cfg.voice_config.provider = os.getenv("STREAMING_AVA_TTS_PROVIDER", cfg.voice_config.provider)
    cfg.voice_config.cosyvoice.api_key = cfg.voice_config.cosyvoice.api_key or os.getenv("STREAMING_AVA_TTS_API_KEY",
                                                                                         "")
    cfg.voice_config.step_fun.api_key = cfg.voice_config.step_fun.api_key or os.getenv("STREAMING_AVA_STEPFUN_API_KEY",
                                                                                       "")
    cfg.voice_config.dou_bao.x_api_key = cfg.voice_config.dou_bao.x_api_key or os.getenv(
        "STREAMING_AVA_DOUBAO_X_API_KEY", "")
    cfg.voice_config.dou_bao.x_api_resource_id = os.getenv(
        "STREAMING_AVA_DOUBAO_X_API_RESOURCE_ID",
        cfg.voice_config.dou_bao.x_api_resource_id,
    )
    cfg.asr_config.provider = os.getenv("STREAMING_AVA_ASR_PROVIDER", cfg.asr_config.provider)
    cfg.asr_config.api_key = cfg.asr_config.api_key or os.getenv("STREAMING_AVA_ASR_API_KEY", "")
    cfg.asr_config.qwen3_asr.api_key = (
            cfg.asr_config.qwen3_asr.api_key
            or os.getenv("STREAMING_AVA_QWEN_ASR_API_KEY", "")
            or cfg.asr_config.api_key
    )
    cfg.asr_config.dou_bao.x_api_key = (
            cfg.asr_config.dou_bao.x_api_key
            or os.getenv("STREAMING_AVA_DOUBAO_ASR_X_API_KEY", "")
            or os.getenv("STREAMING_AVA_DOUBAO_ASR_API_KEY", "")
            or os.getenv("STREAMING_AVA_DOUBAO_ASR_APP_KEY", "")
    )
    cfg.asr_config.dou_bao.x_api_resource_id = os.getenv(
        "STREAMING_AVA_DOUBAO_ASR_X_API_RESOURCE_ID",
        os.getenv("STREAMING_AVA_DOUBAO_ASR_RESOURCE_ID", cfg.asr_config.dou_bao.x_api_resource_id),
    )
    cfg.asr_config.dou_bao.x_api_request_id = os.getenv(
        "STREAMING_AVA_DOUBAO_ASR_X_API_REQUEST_ID",
        os.getenv("STREAMING_AVA_DOUBAO_ASR_REQUEST_ID", cfg.asr_config.dou_bao.x_api_request_id),
    )


settings = load_config()
