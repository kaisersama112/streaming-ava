"""Factories for wiring infrastructure services into the application layer."""

from __future__ import annotations

from pathlib import Path

from ava.capabilities.prompt.prompt_loader import PromptCenter
from ava.capabilities.prompt.prompt_config import PromptCenterConfig
from configs import BASE_DIR, settings


def build_prompt_center(prompt_dir: str | Path | None = None) -> PromptCenter:
    prompt_dir = Path(prompt_dir or settings.runtime.prompt_dir)
    if not prompt_dir.is_absolute():
        prompt_dir = BASE_DIR / prompt_dir
    cfg = PromptCenterConfig(prompt_dir=prompt_dir)
    return PromptCenter(cfg)
