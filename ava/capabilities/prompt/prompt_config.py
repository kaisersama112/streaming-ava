"""PromptCenter 基础配置。"""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PromptCenterConfig:
    """Prompt Skill 根目录配置。"""

    prompt_dir: Path
