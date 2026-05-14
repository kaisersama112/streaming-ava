"""System runtime configuration schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ServerConfig(BaseModel):
    title: str = Field("streaming-ava", description="服务标题")
    host: str = Field("0.0.0.0", description="服务监听地址")
    port: int = Field(7000, description="服务端口")
    reload: bool = Field(False, description="是否自动热重载")
    workers: int = Field(1, description="工作进程数量")


class RuntimeConfig(BaseModel):
    state_file: str = Field("state/memory.json", description="会话状态文件路径")
    default_session_id: str = Field("default", description="默认会话 ID")
    evaluation_log_file: str = Field("state/evaluation.jsonl", description="策略评估日志文件路径")
    trace_log_file: str = Field("state/trace.jsonl", description="结构化追踪日志文件路径")
    trace_log_enabled: bool = Field(True, description="是否启用结构化追踪日志")
    trace_log_asr_partials: bool = Field(True, description="是否记录 ASR partial 事件")
    trace_max_text_chars: int = Field(12000, description="追踪文本字段保留的最大字符数")
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
    agents_sdk_tracing_enabled: bool = Field(False, description="是否启用 Agents SDK tracing")
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
    realtime_tts_done_drain_grace_seconds: float = Field(2.0, description="TTS done 后继续等待尾部音频到达的宽限时间（秒）")
    realtime_tts_close_timeout_seconds: float = Field(45.0, description="流结束后等待 TTS feeder 关闭的最长时间")
    realtime_audio_pump_drain_timeout_seconds: float = Field(45.0, description="TTS 关闭后等待音频泵排空的最长时间")
    realtime_audio_rebuild_on_interrupt: bool = Field(True, description="被打断后是否重建播放流")
    barge_in_partial_chars: int = Field(2, description="触发打断所需的 ASR partial 最小字符数")
    barge_in_stability_threshold: float = Field(0.35, description="触发打断所需的 partial 最小稳定度")
    barge_in_cooldown_ms: int = Field(450, description="两次打断之间的最小间隔（毫秒）")
    echo_detection_window_seconds: float = Field(0.5, description="TTS 最后一帧推出后的时间窗口（秒）")
    echo_detection_min_chars: int = Field(4, description="触发回声检测所需的 ASR partial 最小字符数")
    echo_detection_similarity_threshold: float = Field(0.85, description="回声检测相似度阈值")


class SpeechPostprocessConfig(BaseModel):
    enabled: bool = Field(True, description="是否启用 TTS 前语音后处理")
    math_oralizer_enabled: bool = Field(True, description="是否启用数学 LaTeX 口语化")
    latex_span_only: bool = Field(True, description="是否只替换 LaTeX 片段")
    math_stream_buffer_enabled: bool = Field(True, description="是否启用 LaTeX 感知流缓冲")
    stream_flush_chars: int = Field(72, description="安全缓冲字符数阈值")
