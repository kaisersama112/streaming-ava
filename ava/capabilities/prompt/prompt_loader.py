"""PromptCenter：统一 Prompt Skill 访问入口。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import BaseLoader, Environment

from .parsers import MarkdownAsset, PromptMarkdownParser, SkillParser
from .prompt_config import PromptCenterConfig
from .registry import PromptSkillRegistry
from .specs import Skill
from .store import PromptAssetStore


class PromptCenter:
    """Prompt Skill 中心。"""

    def __init__(self, config: PromptCenterConfig):
        self.config = config
        self.markdown_parser = PromptMarkdownParser()
        self.skill_parser = SkillParser()
        self.registry = PromptSkillRegistry()
        self.store = PromptAssetStore(config.prompt_dir, markdown_parser=self.markdown_parser)
        self._jinja = Environment(
            loader=BaseLoader(),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def _resolve(self, relative_path: str) -> Path:
        return self.store.resolve(relative_path)

    def read_text(self, relative_path: str) -> str:
        """读取任意相对路径文本。"""
        return self.store.read_text(relative_path)

    def load_markdown_asset(self, relative_path: str) -> MarkdownAsset:
        return self.store.load_markdown(relative_path)

    def load_skill(self, skill_file: str) -> Skill:
        """读取并解析单个 Skill。"""
        return self.skill_parser.parse(self.load_markdown_asset(skill_file))

    def resolve_skill_relative_path(self, skill: Skill, relative_path: str) -> str:
        """解析 Skill 内部 references/assets 的相对路径。"""
        return self.registry.resolve_relative(skill.source_file, relative_path)

    def render_path(self, relative_path: str, variables: dict[str, Any] | None = None) -> str:
        """渲染某个文本模板文件。"""
        text = self.read_text(relative_path)
        if not variables:
            return text.strip()
        template = self._jinja.from_string(text)
        return template.render(**variables).strip()
