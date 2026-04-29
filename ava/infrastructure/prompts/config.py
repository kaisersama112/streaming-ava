"""Prompt-center configuration for prompt-plugin assets."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PromptCenterConfig:
    prompt_dir: Path
    router_prompt_file: str = "core/router/router_prompt.md"

    def file_map(self) -> dict[str, str]:
        return {
            "router": self.router_prompt_file,
        }
