"""Prompt 资产解析器。

职责拆分：
- `PromptMarkdownParser`：只负责解析 Markdown frontmatter 与 section
- `PromptSkillCardParser`：只负责解析 `SKILL.md`
- `PromptSpecParser`：只负责解析 `references/spec.md` 正式结构
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

import yaml

from .specs import (
    BranchSpec,
    ModeSpec,
    ModuleSpec,
    PedagogySpec,
    PromptAssetType,
    PromptReferenceEntry,
    PromptSkillCard,
    SubjectSpec,
)

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?", re.DOTALL)
_SECTION_RE = re.compile(r"^##\s+(.+?)\n(.*?)(?=^##\s+|\Z)", re.DOTALL | re.MULTILINE)
_H1_RE = re.compile(r"^#\s+(.+?)\n", re.MULTILINE)
_VALID_PROMPT_ASSET_TYPES: set[str] = {"branch", "mode", "module", "subject", "pedagogy"}


@dataclass(frozen=True)
class MarkdownAsset:
    """已解析的 Markdown 文件。"""

    meta: dict[str, Any]
    title: str
    sections: dict[str, str]
    raw_text: str
    path: str


class PromptMarkdownParser:
    """基础 Markdown 解析器。"""

    def parse(self, *, text: str, path: str) -> MarkdownAsset:
        """解析 Markdown 文本。

        参数：
        - `text`：原始 Markdown 文本
        - `path`：当前文件路径，仅用于错误信息与调试

        返回：
        - `MarkdownAsset`：包含 frontmatter、H1 标题、二级标题 section
        """
        meta, body = self._parse_frontmatter(text)
        title, sections = self._parse_sections(body)
        return MarkdownAsset(
            meta=meta,
            title=title,
            sections=sections,
            raw_text=text,
            path=path,
        )

    def _parse_frontmatter(self, text: str) -> tuple[dict[str, Any], str]:
        match = _FRONTMATTER_RE.match(text)
        if not match:
            return {}, text
        meta = yaml.safe_load(match.group(1)) or {}
        if not isinstance(meta, dict):
            raise ValueError("Frontmatter 必须是对象映射")
        return meta, text[match.end():]

    def _parse_sections(self, body: str) -> tuple[str, dict[str, str]]:
        title_match = _H1_RE.search(body)
        title = title_match.group(1).strip() if title_match else ""
        sections: dict[str, str] = {}
        for match in _SECTION_RE.finditer(body):
            name = match.group(1).strip().lower()
            sections[name] = match.group(2).strip()
        return title, sections


class PromptSkillCardParser:
    """`SKILL.md` 入口卡片解析器。"""

    def parse(self, asset: MarkdownAsset) -> PromptSkillCard:
        """把 `SKILL.md` 解析为轻量技能卡片。"""
        name = str(asset.meta.get("name") or "").strip()
        description = str(asset.meta.get("description") or "").strip()
        if not name:
            raise ValueError(f"{asset.path}: SKILL frontmatter 缺少 `name`")
        if not description:
            raise ValueError(f"{asset.path}: SKILL frontmatter 缺少 `description`")

        asset_meta = dict(asset.meta.get("asset") or {})
        asset_id = str(asset_meta.get("id") or "").strip()
        asset_type = str(asset_meta.get("type") or "").strip()
        entry_reference = str(asset_meta.get("entry") or "references/spec.md").strip()
        if not asset_id:
            raise ValueError(f"{asset.path}: SKILL frontmatter 缺少 `asset.id`")
        if not asset_type:
            raise ValueError(f"{asset.path}: SKILL frontmatter 缺少 `asset.type`")
        if asset_type not in _VALID_PROMPT_ASSET_TYPES:
            raise ValueError(
                f"{asset.path}: `asset.type` 必须是 {_VALID_PROMPT_ASSET_TYPES} 之一，实际得到 {asset_type!r}"
            )

        references: list[PromptReferenceEntry] = []
        for item in list(asset.meta.get("references") or []):
            if not isinstance(item, dict):
                continue
            ref_path = str(item.get("path") or "").strip()
            if not ref_path:
                continue
            references.append(
                PromptReferenceEntry(
                    path=ref_path,
                    purpose=str(item.get("purpose") or "").strip(),
                    when=str(item.get("when") or "").strip(),
                )
            )

        metadata = dict(asset.meta.get("metadata") or {})
        trigger_items = tuple(_parse_list_block(_require_section(asset, "Trigger")))
        procedure_items = tuple(_parse_list_block(_require_section(asset, "Procedure")))
        reference_items = tuple(_parse_list_block(_require_section(asset, "References")))
        decision_notes = tuple(_parse_list_block(asset.sections.get("decision notes", "").strip()))
        return PromptSkillCard(
            name=name,
            description=description,
            asset_id=asset_id,
            asset_type=asset_type,  # type: ignore[arg-type]
            version=int(asset_meta.get("version", 1)),
            entry_reference=entry_reference,
            title=asset.title,
            trigger_items=trigger_items,
            procedure_items=procedure_items,
            reference_items=reference_items,
            decision_notes=decision_notes,
            pattern=str(metadata.get("pattern") or "").strip(),
            load_policy=str(metadata.get("load_policy") or "").strip(),
            references=tuple(references),
            raw={
                "meta": dict(asset.meta),
                "title": asset.title,
                "sections": dict(asset.sections),
            },
        )


def _tupled(items: list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
    return tuple(str(item).strip() for item in (items or []) if str(item).strip())


def _require_meta(asset: MarkdownAsset, key: str) -> Any:
    value = asset.meta.get(key)
    if value in (None, ""):
        raise ValueError(f"{asset.path}: 缺少必填 frontmatter 字段 `{key}`")
    return value


def _require_section(asset: MarkdownAsset, name: str) -> str:
    value = asset.sections.get(name.lower(), "").strip()
    if not value:
        raise ValueError(f"{asset.path}: 缺少必填 section `{name}`")
    return value


def _parse_list_block(text: str) -> list[str]:
    items: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("- "):
            items.append(stripped[2:].strip())
            continue
        if stripped[0].isdigit() and ". " in stripped:
            _, _, rest = stripped.partition(". ")
            items.append(rest.strip())
            continue
        items.append(stripped)
    return items


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    while stripped.startswith("```") and stripped.endswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 2:
            stripped = "\n".join(lines[1:-1]).strip()
            continue
        break
    return stripped


def _parse_scalar_value(text: str) -> Any:
    value = text.strip()
    if not value:
        return ""
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered == "null":
        return None
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar_value(item.strip()) for item in inner.split(",")]
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    if re.fullmatch(r"-?\d+\.\d+", value):
        return float(value)
    return value


def _parse_markdown_mapping(text: str) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        if stripped.startswith("- "):
            stripped = stripped[2:].strip()
        if " = " not in stripped:
            raise ValueError(f"期望 `key = value` 形式的配置行，实际得到：{raw_line!r}")
        key, _, value = stripped.partition(" = ")
        payload[key.strip()] = _parse_scalar_value(value.strip())
    return payload


_RULE_TABLE_SELECT_KEYS = {"select", "use", "target", "route_to"}
_RULE_TABLE_IGNORED_KEYS = {"note", "comment", "备注"}
_RULE_TABLE_WILDCARDS = {"", "-", "*", "any", "任意", "不限"}


def _split_markdown_table_row(line: str) -> list[str]:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [cell.strip().strip("`") for cell in stripped.split("|")]


def _is_markdown_table_separator(line: str) -> bool:
    cells = _split_markdown_table_row(line)
    if not cells:
        return False
    return all(re.fullmatch(r":?-{3,}:?", cell or "") for cell in cells)


def _normalize_rule_table_header(text: str) -> str:
    return re.sub(r"\s+", "_", text.strip().strip("`").lower())


def _parse_rule_table_cell(text: str) -> Any:
    value = text.strip()
    if value.lower() in _RULE_TABLE_WILDCARDS or value in _RULE_TABLE_WILDCARDS:
        return None
    if "," in value and not (value.startswith("[") and value.endswith("]")):
        items = [_parse_scalar_value(item.strip()) for item in value.split(",") if item.strip()]
        return items or None
    return _parse_scalar_value(value)


def _parse_markdown_rule_table(text: str) -> dict[str, Any]:
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) < 2:
        raise ValueError("Markdown 规则表至少需要表头和分隔行")

    headers = [_normalize_rule_table_header(cell) for cell in _split_markdown_table_row(lines[0])]
    if not any(headers):
        raise ValueError("Markdown 规则表缺少表头")
    if not _is_markdown_table_separator(lines[1]):
        raise ValueError("Markdown 规则表缺少分隔行")

    select_index = next((index for index, key in enumerate(headers) if key in _RULE_TABLE_SELECT_KEYS), None)
    if select_index is None:
        raise ValueError("Markdown 规则表必须包含 `select` 列")

    rules: list[dict[str, Any]] = []
    for raw_line in lines[2:]:
        if _is_markdown_table_separator(raw_line):
            continue
        cells = _split_markdown_table_row(raw_line)
        if len(cells) < len(headers):
            cells.extend([""] * (len(headers) - len(cells)))
        elif len(cells) > len(headers):
            cells = cells[: len(headers)]

        selected = cells[select_index].strip()
        if not selected:
            continue

        when: dict[str, Any] = {}
        for key, cell in zip(headers, cells):
            if key in _RULE_TABLE_SELECT_KEYS or key in _RULE_TABLE_IGNORED_KEYS:
                continue
            parsed = _parse_rule_table_cell(cell)
            if parsed is None:
                continue
            when[key] = {"any_of": parsed} if isinstance(parsed, list) else parsed
        rules.append({"when": when, "select": selected})

    return {"rules": rules}


def _parse_markdown_rules(text: str) -> dict[str, Any]:
    rules: list[dict[str, Any]] = []
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        if stripped.startswith("- "):
            stripped = stripped[2:].strip()
        if not stripped.startswith("if "):
            raise ValueError(f"规则行必须以 `if` 开头，实际得到：{raw_line!r}")
        condition_part, sep, select_part = stripped.partition("->")
        if not sep:
            raise ValueError(f"规则行必须包含 `->`，实际得到：{raw_line!r}")
        when: dict[str, Any] = {}
        for clause in re.split(r"\s+and\s+", condition_part[3:].strip()):
            clause = clause.strip()
            if not clause:
                continue
            if " in " in clause:
                key, _, value = clause.partition(" in ")
                when[key.strip()] = {"any_of": _parse_scalar_value(value.strip())}
                continue
            if " = " in clause:
                key, _, value = clause.partition(" = ")
                when[key.strip()] = _parse_scalar_value(value.strip())
                continue
            raise ValueError(f"暂不支持的规则条件：{clause!r}")
        rules.append({"when": when, "select": select_part.strip()})
    return {"rules": rules}


def _parse_mapping_block(text: str) -> dict[str, Any]:
    stripped = _strip_code_fence(text)
    if not stripped:
        return {}

    first_line = next((line.strip() for line in stripped.splitlines() if line.strip()), "")
    if first_line.startswith("rules:"):
        payload = yaml.safe_load(stripped) or {}
    elif first_line.startswith("|"):
        payload = _parse_markdown_rule_table(stripped)
    elif first_line.startswith("if ") or first_line.startswith("- if "):
        payload = _parse_markdown_rules(stripped)
    elif " = " in first_line or first_line.startswith("- "):
        payload = _parse_markdown_mapping(stripped)
    else:
        payload = yaml.safe_load(stripped) or {}

    if not isinstance(payload, dict):
        raise ValueError("配置块必须解析为对象映射")
    return payload


class PromptSpecParser:
    """正式结构资产解析器。"""

    def parse_branch(self, asset: MarkdownAsset) -> BranchSpec:
        if asset.meta.get("type") != "branch":
            raise ValueError(f"{asset.path}: 期望 `type=branch`")
        raw = {
            "meta": dict(asset.meta),
            "purpose": _require_section(asset, "Purpose"),
            "rules": _parse_list_block(_require_section(asset, "Rules")),
        }
        return BranchSpec(
            asset_id=str(_require_meta(asset, "id")),
            version=int(asset.meta.get("version", 1)),
            name=_require_section(asset, "Name"),
            purpose=raw["purpose"],
            rules=_tupled(raw["rules"]),
            raw=raw,
        )

    def parse_module(self, asset: MarkdownAsset) -> ModuleSpec:
        if asset.meta.get("type") != "module":
            raise ValueError(f"{asset.path}: 期望 `type=module`")
        # defaults = _module_defaults(str(_require_meta(asset, "id")))
        raw = {
            "meta": dict(asset.meta),
            "goal": _require_section(asset, "Goal"),
            "applies_to": _parse_list_block(_require_section(asset, "Applies To")),
            "response_structure": _parse_list_block(_require_section(asset, "Response Structure")),
            "global_rules": _parse_list_block(_require_section(asset, "Global Rules")),
            "interaction_policy": _parse_list_block(_require_section(asset, "Interaction Policy")),
            "output_defaults": _parse_mapping_block(_require_section(asset, "Output Defaults")),
            "instructions": _parse_list_block(_require_section(asset, "Instructions")),
        }
        return ModuleSpec(
            asset_id=str(_require_meta(asset, "id")),
            version=int(asset.meta.get("version", 1)),
            name=_require_section(asset, "Name"),
            goal=raw["goal"],
            applies_to=_tupled(raw["applies_to"]),
            response_structure=_tupled(raw["response_structure"]),
            global_rules=_tupled(raw["global_rules"]),
            interaction_policy=_tupled(raw["interaction_policy"]),
            output_defaults=dict(raw["output_defaults"]),
            instructions=_tupled(raw["instructions"]),
            capabilities=_tupled(asset.meta.get("capabilities")),
            supports_modalities=_tupled(asset.meta.get("supports_modalities")),
            supports_question_kinds=_tupled(asset.meta.get("supports_question_kinds")),
            raw=raw,
        )

    def parse_subject(self, asset: MarkdownAsset) -> SubjectSpec:
        if asset.meta.get("type") != "subject":
            raise ValueError(f"{asset.path}: 期望 `type=subject`")
        # defaults = _subject_defaults(str(_require_meta(asset, "id")))
        raw = {
            "meta": dict(asset.meta),
            "focus": _parse_list_block(_require_section(asset, "Focus")),
            "explanation_strategy": _parse_list_block(_require_section(asset, "Explanation Strategy")),
            "common_mistakes": _parse_list_block(_require_section(asset, "Common Mistakes")),
            "evidence_preference": _parse_list_block(_require_section(asset, "Evidence Preference")),
            "ui_hints": _parse_mapping_block(_require_section(asset, "UI Hints")),
            "instructions": _parse_list_block(_require_section(asset, "Instructions")),
        }
        return SubjectSpec(
            asset_id=str(_require_meta(asset, "id")),
            version=int(asset.meta.get("version", 1)),
            name=_require_section(asset, "Name"),
            focus=_tupled(raw["focus"]),
            explanation_strategy=_tupled(raw["explanation_strategy"]),
            common_mistakes=_tupled(raw["common_mistakes"]),
            evidence_preference=_tupled(raw["evidence_preference"]),
            ui_hints=dict(raw["ui_hints"]),
            instructions=_tupled(raw["instructions"]),
            capabilities=_tupled(asset.meta.get("capabilities")),
            supports_artifacts=_tupled(asset.meta.get("supports_artifacts")),
            raw=raw,
        )

    def parse_pedagogy(self, asset: MarkdownAsset) -> PedagogySpec:
        if asset.meta.get("type") != "pedagogy":
            raise ValueError(f"{asset.path}: 期望 `type=pedagogy`")
        asset_id = str(_require_meta(asset, "id"))
        raw = {
            "meta": dict(asset.meta),
            "tone": _require_section(asset, "Tone"),
            "constraints": _parse_list_block(_require_section(asset, "Constraints")),
            "output_adjustments": _parse_mapping_block(_require_section(asset, "Output Adjustments")),
            "instructions": _parse_list_block(_require_section(asset, "Instructions")),
        }
        return PedagogySpec(
            asset_id=asset_id,
            version=int(asset.meta.get("version", 1)),
            name=_require_section(asset, "Name"),
            tone=raw["tone"],
            constraints=_tupled(raw["constraints"]),
            output_adjustments=dict(raw["output_adjustments"]),
            instructions=_tupled(raw["instructions"]),
            pedagogy_traits=_tupled(asset.meta.get("pedagogy_traits")),
            raw=raw,
        )

    def parse_mode(self, asset: MarkdownAsset) -> ModeSpec:
        if asset.meta.get("type") != "mode":
            raise ValueError(f"{asset.path}: 期望 `type=mode`")
        raw = {
            "meta": dict(asset.meta),
            "description": _require_section(asset, "Description"),
            "delivery_mode": _require_section(asset, "Delivery Mode"),
            "ui_mode": _require_section(asset, "UI Mode"),
            "response_shape": _require_section(asset, "Response Shape"),
            "objective": _require_section(asset, "Objective"),
            "instructions": _parse_list_block(_require_section(asset, "Instructions")),
            "interaction_rules": _parse_list_block(_require_section(asset, "Interaction Rules")),
            "examples": _parse_list_block(_require_section(asset, "Examples")),
            "response_contract": _parse_mapping_block(_require_section(asset, "Response Contract")),
            "speech_policy": _parse_mapping_block(_require_section(asset, "Speech Policy")),
            "ui_policy": (
                _parse_mapping_block(asset.sections["ui policy"])
                if asset.sections.get("ui policy", "").strip()
                else {}
            ),
        }
        return ModeSpec(
            asset_id=str(_require_meta(asset, "id")),
            version=int(asset.meta.get("version", 1)),
            name=_require_section(asset, "Name"),
            description=raw["description"],
            delivery_mode=raw["delivery_mode"],
            ui_mode=raw["ui_mode"],
            response_shape=raw["response_shape"],
            objective=raw["objective"],
            instructions=_tupled(raw["instructions"]),
            interaction_rules=_tupled(raw["interaction_rules"]),
            examples=_tupled(raw["examples"]),
            response_contract=dict(raw["response_contract"]),
            speech_policy=dict(raw["speech_policy"]),
            ui_policy=dict(raw["ui_policy"]),
            raw=raw,
        )
