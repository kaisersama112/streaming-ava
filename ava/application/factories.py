"""Factories for wiring infrastructure services into the application layer."""

from __future__ import annotations

from pathlib import Path

from ava.application.routing import RouterService
from ava.infrastructure.prompts import PromptCenter, PromptCenterConfig
from config import BASE_DIR, settings


def build_prompt_center(prompt_dir: str | Path | None = None) -> PromptCenter:
    prompt_dir = Path(prompt_dir or settings.runtime.prompt_dir)
    if not prompt_dir.is_absolute():
        prompt_dir = BASE_DIR / prompt_dir
    cfg = PromptCenterConfig(prompt_dir=prompt_dir)
    return PromptCenter(cfg)


def build_router(
    prompt_center: PromptCenter,
    api_base: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
    timeout: int | None = None,
) -> RouterService:
    return RouterService(
        api_base=api_base or settings.openai_config.api_base,
        api_key=api_key or settings.openai_config.api_key,
        model=model or settings.runtime.router_model or settings.openai_config.model or settings.openai_config.intent_model,
        timeout=timeout or settings.runtime.router_timeout,
        prompt_center=prompt_center,
    )
