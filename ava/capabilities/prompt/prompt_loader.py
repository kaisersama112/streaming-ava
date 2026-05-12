"""Prompt loader, markdown asset parser, and Jinja renderer."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from jinja2 import BaseLoader, Environment

from .prompt_config import PromptCenterConfig

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?", re.DOTALL)
_SECTION_RE = re.compile(r"^##\s+(.+?)\n(.*?)(?=^##\s+|\Z)", re.DOTALL | re.MULTILINE)
_H1_RE = re.compile(r"^#\s+(.+?)\n", re.MULTILINE)


@dataclass(frozen=True)
class MarkdownAsset:
    meta: dict[str, Any]
    title: str
    sections: dict[str, str]
    raw_text: str
    path: str


class PromptCenter:
    def __init__(self, config: PromptCenterConfig):
        self.config = config
        self._cache: dict[str, str] = {}
        self._yaml_cache: dict[str, Any] = {}
        self._markdown_cache: dict[str, MarkdownAsset] = {}
        self._jinja = Environment(
            loader=BaseLoader(),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def _resolve(self, relative_path: str) -> Path:
        return Path(self.config.prompt_dir) / relative_path

    def get(self, name: str) -> str:
        if name in self._cache:
            return self._cache[name]

        file_name = self.config.file_map().get(name, name)
        if not file_name:
            raise KeyError(f"Unknown prompt name: {name}")

        path = self._resolve(file_name)
        if not path.exists():
            raise FileNotFoundError(f"Prompt file not found: {path}")

        text = path.read_text(encoding="utf-8").strip()
        self._cache[name] = text
        return text

    def load_yaml(self, relative_path: str) -> Any:
        if relative_path in self._yaml_cache:
            return self._yaml_cache[relative_path]

        path = self._resolve(relative_path)
        if not path.exists():
            raise FileNotFoundError(f"Prompt yaml file not found: {path}")

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        self._yaml_cache[relative_path] = data
        return data

    def load_markdown_asset(self, relative_path: str) -> MarkdownAsset:
        if relative_path in self._markdown_cache:
            return self._markdown_cache[relative_path]

        path = self._resolve(relative_path)
        if not path.exists():
            raise FileNotFoundError(f"Prompt markdown file not found: {path}")

        raw = path.read_text(encoding="utf-8")
        if not raw.strip():
            raise ValueError(f"Prompt markdown file is empty: {path}")

        meta, body = self._parse_frontmatter(raw)
        title, sections = self._parse_sections(body)
        asset = MarkdownAsset(
            meta=meta,
            title=title,
            sections=sections,
            raw_text=raw,
            path=str(path),
        )
        self._markdown_cache[relative_path] = asset
        return asset

    def load_markdown_sections(self, relative_path: str) -> dict[str, str]:
        return self.load_markdown_asset(relative_path).sections

    def _parse_frontmatter(self, text: str) -> tuple[dict[str, Any], str]:
        match = _FRONTMATTER_RE.match(text)
        if not match:
            return {}, text
        meta = yaml.safe_load(match.group(1)) or {}
        if not isinstance(meta, dict):
            raise ValueError("Frontmatter must be a mapping")
        return meta, text[match.end():]

    def _parse_sections(self, body: str) -> tuple[str, dict[str, str]]:
        title_match = _H1_RE.search(body)
        title = title_match.group(1).strip() if title_match else ""
        sections: dict[str, str] = {}
        for match in _SECTION_RE.finditer(body):
            name = match.group(1).strip().lower()
            sections[name] = match.group(2).strip()
        return title, sections

    def render(self, name: str, variables: dict[str, Any] | None = None) -> str:
        text = self.get(name)
        if not variables:
            return text
        template = self._jinja.from_string(text)
        return template.render(**variables).strip()

    def render_path(self, relative_path: str, variables: dict[str, Any] | None = None) -> str:
        return self.render(relative_path, variables)
