"""PromptCenter：Prompt 资产统一入口。

职责：
- 读取 `prompt-plugin/` 下的模板与 Skill 资产
- 提供 Jinja 渲染能力
- 为上层 loader 暴露轻量 Skill 卡片与正式结构引用入口
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import BaseLoader, Environment

from .parsers import MarkdownAsset, PromptMarkdownParser, PromptSkillCardParser, PromptSpecParser
from .prompt_config import PromptCenterConfig
from .registry import PromptSkillRegistry
from .specs import PromptSkillCard
from .store import PromptAssetStore


class PromptCenter:
    """Prompt 资产统一访问入口。"""

    def __init__(self, config: PromptCenterConfig):
        self.config = config
        self.markdown_parser = PromptMarkdownParser()
        self.skill_card_parser = PromptSkillCardParser()
        self.spec_parser = PromptSpecParser()
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

    def get(self, name: str) -> str:
        file_name = self.config.file_map().get(name, name)
        if not file_name:
            raise KeyError(f"Unknown prompt name: {name}")
        return self.store.read_text(file_name).strip()

    def load_yaml(self, relative_path: str) -> Any:
        return self.store.load_yaml(relative_path)

    def load_markdown_asset(self, relative_path: str) -> MarkdownAsset:
        return self.store.load_markdown(relative_path)

    def load_markdown_sections(self, relative_path: str) -> dict[str, str]:
        return self.load_markdown_asset(relative_path).sections

    def load_skill_card(self, skill_file: str) -> PromptSkillCard:
        """读取 `SKILL.md` 轻量技能卡片。"""
        return self.skill_card_parser.parse(self.load_markdown_asset(skill_file))

    def load_skill_reference_asset(self, skill_file: str, relative_path: str) -> MarkdownAsset:
        """从 Skill 目录内继续读取按需引用文件。"""
        resolved = self.registry.resolve_relative(skill_file, relative_path)
        return self.load_markdown_asset(resolved)

    def render(self, name: str, variables: dict[str, Any] | None = None) -> str:
        text = self.get(name)
        if not variables:
            return text
        template = self._jinja.from_string(text)
        return template.render(**variables).strip()

    def render_path(self, relative_path: str, variables: dict[str, Any] | None = None) -> str:
        return self.render(relative_path, variables)
