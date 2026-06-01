"""Prompt Skill 文件访问层。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .parsers import MarkdownAsset, PromptMarkdownParser


class PromptAssetStore:
    """负责 Prompt Skill 文件读取与缓存。"""

    def __init__(self, root_dir: Path, *, markdown_parser: PromptMarkdownParser | None = None) -> None:
        self.root_dir = Path(root_dir)
        self.markdown_parser = markdown_parser or PromptMarkdownParser()
        self._text_cache: dict[str, str] = {}
        self._markdown_cache: dict[str, MarkdownAsset] = {}

    def resolve(self, relative_path: str) -> Path:
        """解析仓库内相对路径。"""
        return self.root_dir / relative_path

    def read_text(self, relative_path: str) -> str:
        """读取 UTF-8 文本文件。"""
        if relative_path in self._text_cache:
            return self._text_cache[relative_path]
        path = self.resolve(relative_path)
        if not path.exists():
            raise FileNotFoundError(f"Prompt 文件不存在：{path}")
        text = path.read_text(encoding="utf-8")
        self._text_cache[relative_path] = text
        return text

    def load_markdown(self, relative_path: str) -> MarkdownAsset:
        """读取并解析 Markdown 资产。"""
        if relative_path in self._markdown_cache:
            return self._markdown_cache[relative_path]
        path = self.resolve(relative_path)
        if not path.exists():
            raise FileNotFoundError(f"Prompt Markdown 不存在：{path}")
        raw = path.read_text(encoding="utf-8")
        if not raw.strip():
            raise ValueError(f"Prompt Markdown 为空：{path}")
        asset = self.markdown_parser.parse(text=raw, path=relative_path)
        self._markdown_cache[relative_path] = asset
        return asset
