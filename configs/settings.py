from pathlib import Path
from typing import Any, Optional
import os
import yaml
from pydantic import BaseModel, Field

from configs.model import ASRConfig, BigModelConfig, OpenAIConfig
from configs.system import RuntimeConfig, ServerConfig, SpeechPostprocessConfig
from configs.tts import VoiceConfig

BASE_DIR = Path(__file__).resolve().parent.parent


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
    cfg.voice_config.cosyvoice.api_key = cfg.voice_config.cosyvoice.api_key or os.getenv("STREAMING_AVA_TTS_API_KEY", "")
    cfg.voice_config.step_fun.api_key = cfg.voice_config.step_fun.api_key or os.getenv("STREAMING_AVA_STEPFUN_API_KEY", "")
    cfg.voice_config.dou_bao.x_api_key = cfg.voice_config.dou_bao.x_api_key or os.getenv("STREAMING_AVA_DOUBAO_X_API_KEY", "")
    cfg.voice_config.dou_bao.x_api_resource_id = os.getenv(
        "STREAMING_AVA_DOUBAO_X_API_RESOURCE_ID",
        cfg.voice_config.dou_bao.x_api_resource_id,
    )
    cfg.asr_config.api_key = cfg.asr_config.api_key or os.getenv("STREAMING_AVA_ASR_API_KEY", "")


settings = load_config()
