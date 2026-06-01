"""Prompt 资产文件存储层。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .parsers import MarkdownAsset, PromptMarkdownParser


class PromptAssetStore:
    """负责文件读取、路径解析与缓存。

    该类不理解任何业务语义，只做确定性文件访问。
    """

    def __init__(self, root_dir: Path, *, markdown_parser: PromptMarkdownParser | None = None) -> None:
        self.root_dir = Path(root_dir)
        self.markdown_parser = markdown_parser
        self._text_cache: dict[str, str] = {}
        self._yaml_cache: dict[str, Any] = {}
        self._markdown_cache: dict[str, MarkdownAsset] = {}

    def resolve(self, relative_path: str) -> Path:
        """把仓库内相对路径解析为绝对路径。"""
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

    def load_yaml(self, relative_path: str) -> Any:
        """读取 YAML 文件。"""
        if relative_path in self._yaml_cache:
            return self._yaml_cache[relative_path]
        path = self.resolve(relative_path)
        if not path.exists():
            raise FileNotFoundError(f"Prompt YAML 不存在：{path}")
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        self._yaml_cache[relative_path] = data
        return data

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
        asset = self.markdown_parser.parse(text=raw, path=str(path))
        self._markdown_cache[relative_path] = asset
        return asset
