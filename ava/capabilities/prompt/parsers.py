"""Prompt Skill 解析器。"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

import yaml

from .specs import Skill


_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?", re.DOTALL)
_SECTION_RE = re.compile(r"^#\s+(.+?)\n(.*?)(?=^#\s+|\Z)", re.DOTALL | re.MULTILINE)
_VALID_SKILL_KINDS = {"capability", "task", "knowledge", "method", "audience"}


@dataclass(frozen=True)
class MarkdownAsset:
    """已解析 Markdown 文件。"""

    meta: dict[str, Any]
    sections: dict[str, str]
    raw_text: str
    path: str


class PromptMarkdownParser:
    """基础 Markdown 解析器。"""

    def parse(self, *, text: str, path: str) -> MarkdownAsset:
        """解析 Markdown 文件内容。"""
        meta, body = self._parse_frontmatter(text)
        sections = self._parse_sections(body)
        return MarkdownAsset(
            meta=meta,
            sections=sections,
            raw_text=text,
            path=path,
        )

    @staticmethod
    def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
        match = _FRONTMATTER_RE.match(text)
        if not match:
            raise ValueError("Skill 文件缺少 frontmatter")
        meta = yaml.safe_load(match.group(1)) or {}
        if not isinstance(meta, dict):
            raise ValueError("Frontmatter 必须是对象映射")
        return meta, text[match.end() :]

    @staticmethod
    def _parse_sections(body: str) -> dict[str, str]:
        sections: dict[str, str] = {}
        for match in _SECTION_RE.finditer(body):
            sections[match.group(1).strip().lower()] = match.group(2).strip()
        return sections


class SkillParser:
    """统一 Skill 解析器。"""

    _REQUIRED_SECTIONS = ("purpose", "instructions", "references", "examples")

    def parse(self, asset: MarkdownAsset) -> Skill:
        """把 `SKILL.md` 解析成统一 Skill 对象。"""
        meta = dict(asset.meta)
        name = str(meta.get("name") or "").strip()
        description = str(meta.get("description") or "").strip()
        asset_meta = dict(meta.get("asset") or {})
        kind = str(asset_meta.get("kind") or "").strip()
        version = str(meta.get("version") or "").strip()
        load_policy = str(meta.get("load_policy") or "").strip()
        references = tuple(self._normalize_path_list(meta.get("references")))
        assets = tuple(self._normalize_path_list(meta.get("assets")))

        if not name:
            raise ValueError(f"{asset.path}: 缺少 `name`")
        if not description:
            raise ValueError(f"{asset.path}: 缺少 `description`")
        if kind not in _VALID_SKILL_KINDS:
            raise ValueError(f"{asset.path}: `asset.kind` 非法：{kind!r}")
        if not version:
            raise ValueError(f"{asset.path}: 缺少 `version`")
        if load_policy not in {"preload", "on_demand"}:
            raise ValueError(f"{asset.path}: `load_policy` 非法：{load_policy!r}")

        sections = dict(asset.sections)
        for key in self._REQUIRED_SECTIONS:
            if not str(sections.get(key, "") or "").strip():
                raise ValueError(f"{asset.path}: 缺少 section `# {key.title()}`")

        return Skill(
            name=name,
            description=description,
            kind=kind,  # type: ignore[arg-type]
            version=version,
            load_policy=load_policy,
            purpose=str(sections["purpose"]).strip(),
            instructions=str(sections["instructions"]).strip(),
            references=references,
            assets=assets,
            examples=tuple(_list_items(sections["examples"])),
            source_file=asset.path,
            raw={
                "meta": meta,
                "sections": sections,
            },
        )

    @staticmethod
    def _normalize_path_list(value: Any) -> list[str]:
        if not isinstance(value, list):
            raise ValueError("`references` 和 `assets` 必须是数组")
        result: list[str] = []
        for item in value:
            text = str(item or "").strip()
            if text:
                result.append(text)
        return result


def _list_items(text: str) -> list[str]:
    items: list[str] = []
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("- "):
            items.append(line[2:].strip())
            continue
        items.append(line)
    return items
