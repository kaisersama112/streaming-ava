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
    trace_log_file: str = Field("state/trace.jsonl", description="统一全链路 trace 日志路径")
    trace_enabled: bool = Field(True, description="是否启用统一 trace 埋点")
    multi_intent_enabled: bool = Field(False, description="是否启用多意图技能子 Agent 编排路径")
    context_runtime_injection: bool = Field(True, description="是否向模型注入运行时状态/记忆投影")
    visual_continuity_max_turns: int = Field(2, description="纯文字追问可继承视觉上下文的最近轮次范围")
    route_cache_enabled: bool = Field(True, description="是否缓存相同输入指纹的路由结果")
    route_cache_ttl_seconds: int = Field(120, description="路由结果缓存有效期（秒）")
    parallel_prefetch_enabled: bool = Field(True, description="是否并行预取历史摘要/PromptPackage 等无依赖资源")
    responder_continuity_enabled: bool = Field(False, description="是否启用 Responses API previous_response_id 连续对话")
    model_selection_enabled: bool = Field(True, description="是否按复杂度与置信度动态选模")
    small_model: str = Field("", description="简单高置信轮次使用的小模型（端侧或便宜云模型）")
    fallback_model: str = Field("", description="兜底大模型名称")
    model_selection_min_confidence: float = Field(0.75, description="走小模型所需的最低路由置信度")
    agents_sdk_orchestration_mode: str = Field("serial", description="技能子 Agent 编排模式：serial/parallel/conditional")


class IntentLocalConfig(BaseModel):
    runtime: str = Field("llama_cpp", description="端侧运行时：llama_cpp / onnx / mnn（均暴露 OpenAI 兼容接口）")
    api_base: str = Field("http://127.0.0.1:8080/v1", description="端侧推理服务 OpenAI 兼容地址")
    api_key: str = Field("", description="端侧推理服务密钥（本地通常为空）")
    model: str = Field("qwen3-4b-router", description="端侧路由小模型名称")
    timeout_ms: int = Field(700, description="端侧路由首 token 超时（毫秒），超时即云侧兜底")
    threads: int = Field(0, description="推理线程数，0 表示运行时自动")
    n_gpu_layers: int = Field(0, description="llama.cpp GPU 卸载层数")
    ctx_size: int = Field(4096, description="端侧上下文长度")
    kv_cache_reuse: bool = Field(True, description="是否复用 KV Cache（llama.cpp --cache-reuse）")
    no_think: bool = Field(True, description="Qwen3 系列是否关闭思考模式（/no_think）")


class IntentConfig(BaseModel):
    enabled: bool = Field(False, description="是否启用端云协同路由链路")
    provider: str = Field("api", description="路由 provider：api（云）/ local（端侧小模型）")
    local: IntentLocalConfig = Field(default_factory=IntentLocalConfig)
    cloud_fallback_enabled: bool = Field(True, description="端侧失败/低置信时是否降级云侧")
    min_confidence: float = Field(0.6, description="低于该置信度触发云侧复核")
    cache_enabled: bool = Field(True, description="是否缓存路由结果")
    cache_ttl_seconds: int = Field(120, description="路由缓存有效期（秒）")


class Config(BaseModel):
    config_files: list[str] = Field(default_factory=list, description="额外配置文件，按顺序加载后由主配置覆盖")
    server: ServerConfig = Field(default_factory=ServerConfig)
    openai_config: OpenAIConfig = Field(default_factory=OpenAIConfig)
    bigmodel_config: BigModelConfig = Field(default_factory=BigModelConfig)
    voice_config: VoiceConfig = Field(default_factory=VoiceConfig)
    asr_config: ASRConfig = Field(default_factory=ASRConfig)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    intent_config: IntentConfig = Field(default_factory=IntentConfig)
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


def _local_overlay_path(path: Path) -> Path:
    """根据 xxx.yaml 推导出 xxx.local.yaml（本地密钥覆盖文件，不入库）。"""
    return path.with_name(path.stem + ".local" + path.suffix)


def _load_with_includes(path: Path, *, seen: set[Path] | None = None) -> dict[str, Any]:
    resolved = path.resolve()
    seen = seen or set()
    if resolved in seen:
        return {}
    seen.add(resolved)

    raw_config = _read_yaml(resolved)
    # 本地覆盖：xxx.local.yaml 覆盖同名 xxx.yaml（用于放真实密钥，已被 .gitignore 忽略）
    raw_config = _deep_merge(raw_config, _read_yaml(_local_overlay_path(resolved)))
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
    cfg.bigmodel_config.api_key = cfg.bigmodel_config.api_key or os.getenv("STREAMING_AVA_BIGMODEL_API_KEY", "")
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
    cfg.intent_config.provider = os.getenv("STREAMING_AVA_INTENT_PROVIDER", cfg.intent_config.provider)
    cfg.intent_config.enabled = os.getenv(
        "STREAMING_AVA_INTENT_ENABLED", "true" if cfg.intent_config.enabled else "false"
    ).lower() in {"1", "true", "yes", "on"}
    cfg.intent_config.local.api_base = os.getenv(
        "STREAMING_AVA_INTENT_LOCAL_API_BASE", cfg.intent_config.local.api_base
    )
    cfg.intent_config.local.model = os.getenv("STREAMING_AVA_INTENT_LOCAL_MODEL", cfg.intent_config.local.model)
    cfg.runtime.small_model = os.getenv("STREAMING_AVA_SMALL_MODEL", cfg.runtime.small_model)
    cfg.runtime.fallback_model = os.getenv("STREAMING_AVA_FALLBACK_MODEL", cfg.runtime.fallback_model)


settings = load_config()
