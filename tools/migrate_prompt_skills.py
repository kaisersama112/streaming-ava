"""批量迁移 prompt-plugin 资产到统一 Skill 合同。

该脚本只服务于当前仓库内的 prompt-plugin 目录重构：
- 把旧目录结构重写为 `capabilities/` + `components/`
- 把旧版 `SKILL.md` 改写为统一合同 v1
- 把旧版 `references/spec.md` 改写为统一说明模板

脚本是一次性迁移工具，不参与运行时逻辑。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import shutil
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
PROMPT_ROOT = ROOT / "prompt-plugin"

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?", re.DOTALL)
OLD_SECTION_RE = re.compile(r"^##\s+(.+?)\n(.*?)(?=^##\s+|\Z)", re.DOTALL | re.MULTILINE)
NEW_SECTION_RE = re.compile(r"^#\s+(.+?)\n(.*?)(?=^#\s+|\Z)", re.DOTALL | re.MULTILINE)


@dataclass(frozen=True)
class SourceAsset:
    """单个旧 Prompt 资产来源。"""

    target_kind: str
    target_name: str
    target_dir: Path
    source_skill_candidates: tuple[Path, ...]
    source_spec_candidates: tuple[Path, ...]
    display_name: str


def _first_existing(paths: tuple[Path, ...]) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


def _parse_markdown(path: Path, *, old_style: bool) -> tuple[dict[str, Any], dict[str, str]]:
    text = path.read_text(encoding="utf-8")
    meta: dict[str, Any] = {}
    body = text
    match = FRONTMATTER_RE.match(text)
    if match:
        meta = yaml.safe_load(match.group(1)) or {}
        body = text[match.end() :]
    section_re = OLD_SECTION_RE if old_style else NEW_SECTION_RE
    sections: dict[str, str] = {}
    for section_match in section_re.finditer(body):
        sections[section_match.group(1).strip().lower()] = section_match.group(2).strip()
    return meta, sections


def _list_items(text: str) -> list[str]:
    items: list[str] = []
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("- "):
            items.append(line[2:].strip())
            continue
        if re.match(r"^\d+\.\s+", line):
            items.append(re.sub(r"^\d+\.\s+", "", line))
            continue
        items.append(line)
    return items


def _format_bullets(items: list[str]) -> str:
    normalized = [item.strip() for item in items if item and item.strip()]
    if not normalized:
        return "- 无"
    return "\n".join(f"- {item}" for item in normalized)


def _dedupe(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        value = item.strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _normalize_name(value: str) -> str:
    text = str(value or "").strip()
    text = text.replace("_", "-").replace(" ", "-")
    text = re.sub(r"[^a-zA-Z0-9\-]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-").lower()
    return text


def _strip_frontmatter(text: str) -> str:
    match = FRONTMATTER_RE.match(text)
    return text[match.end() :].strip() if match else text.strip()


def _build_skill_markdown(asset: SourceAsset, skill_meta: dict[str, Any], skill_sections: dict[str, str], spec_sections: dict[str, str]) -> str:
    description = str(skill_meta.get("description") or "").strip()
    if not description:
        description = f"{asset.display_name}。"

    purpose_lines: list[str] = []
    if asset.target_kind == "capability":
        purpose_lines.append(description)
        if spec_sections.get("purpose"):
            purpose_lines.append(spec_sections["purpose"])
    elif asset.target_kind == "task":
        purpose_lines.append(description)
        for key in ("objective", "goal", "description"):
            if spec_sections.get(key):
                purpose_lines.append(spec_sections[key])
                break
    elif asset.target_kind == "knowledge":
        purpose_lines.append(description)
        if spec_sections.get("focus"):
            purpose_lines.append("该知识 Skill 关注以下内容：")
            purpose_lines.extend(_list_items(spec_sections["focus"]))
    elif asset.target_kind == "method":
        purpose_lines.append(description)
        if spec_sections.get("tone"):
            purpose_lines.append(f"默认表达风格：{spec_sections['tone']}")

    instruction_items: list[str] = []
    for key in ("procedure", "rules", "instructions", "global rules", "interaction rules", "constraints", "interaction policy", "explanation strategy", "evidence preference"):
        instruction_items.extend(_list_items(skill_sections.get(key, "")))
        instruction_items.extend(_list_items(spec_sections.get(key, "")))
    if not instruction_items and spec_sections.get("detailed rules"):
        instruction_items.extend(_list_items(spec_sections["detailed rules"]))
    instruction_items = _dedupe(instruction_items)

    example_items: list[str] = []
    for key in ("trigger", "examples", "common mistakes", "decision notes"):
        example_items.extend(_list_items(skill_sections.get(key, "")))
        example_items.extend(_list_items(spec_sections.get(key, "")))
    example_items = _dedupe(example_items)

    reference_lines = ["- `references/spec.md`：当前 Skill 的详细规范说明。"]

    frontmatter = {
        "name": asset.target_name,
        "description": description,
        "asset": {"kind": asset.target_kind},
        "version": "1.0.0",
        "load_policy": "on_demand",
        "references": ["references/spec.md"],
        "assets": [],
    }
    frontmatter_text = yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False).strip()
    purpose_text = "\n\n".join(_dedupe(purpose_lines)).strip() or "说明当前 Skill 的核心目标。"
    references_text = "\n".join(reference_lines)
    examples_text = _format_bullets(example_items)
    instructions_text = _format_bullets(instruction_items)
    return (
        f"---\n{frontmatter_text}\n---\n\n"
        f"# Purpose\n\n{purpose_text}\n\n"
        f"# Instructions\n\n{instructions_text}\n\n"
        f"# References\n\n{references_text}\n\n"
        f"# Examples\n\n{examples_text}\n"
    )


def _build_spec_markdown(asset: SourceAsset, skill_sections: dict[str, str], spec_path: Path | None, spec_meta: dict[str, Any], spec_sections: dict[str, str]) -> str:
    overview_lines: list[str] = [
        f"该文档描述 `{asset.target_name}` Skill 的详细规范与扩展说明。",
    ]
    if skill_sections.get("references"):
        overview_lines.extend(_list_items(skill_sections["references"]))
    if spec_sections.get("name"):
        overview_lines.append(f"旧资产名称：{spec_sections['name']}")

    detail_items: list[str] = []
    for key in (
        "purpose",
        "rules",
        "goal",
        "response structure",
        "global rules",
        "interaction policy",
        "focus",
        "explanation strategy",
        "common mistakes",
        "evidence preference",
        "constraints",
        "instructions",
        "description",
        "objective",
    ):
        value = spec_sections.get(key, "")
        if value:
            detail_items.append(f"## {key.title()}\n\n{value.strip()}")
    if not detail_items:
        detail_items.append("当前 Skill 暂无额外长规则。")

    rendering_items: list[str] = []
    for key in ("output defaults", "response contract", "speech policy", "ui policy", "ui hints", "output adjustments"):
        value = spec_sections.get(key, "")
        if value:
            rendering_items.append(f"## {key.title()}\n\n{value.strip()}")
    if not rendering_items:
        rendering_items.append("当前 Skill 没有额外渲染注意事项。")

    asset_notes = "当前 Skill 没有声明额外 assets。" if not spec_path else "如需扩展模板或示例，请放入当前 Skill 的 `assets/` 目录。"

    example_items: list[str] = []
    for key in ("examples", "trigger"):
        example_items.extend(_list_items(skill_sections.get(key, "")))
        example_items.extend(_list_items(spec_sections.get(key, "")))
    example_text = _format_bullets(_dedupe(example_items))

    return (
        "# Overview\n\n"
        + "\n\n".join(_dedupe(overview_lines)).strip()
        + "\n\n# Detailed Rules\n\n"
        + "\n\n".join(detail_items).strip()
        + "\n\n# Rendering Notes\n\n"
        + "\n\n".join(rendering_items).strip()
        + "\n\n# Asset Notes\n\n"
        + asset_notes
        + "\n\n# Examples\n\n"
        + example_text
        + "\n"
    )


def _write_skill(asset: SourceAsset) -> None:
    source_skill = _first_existing(asset.source_skill_candidates)
    if source_skill is None:
        raise FileNotFoundError(f"找不到源 Skill 文件：{asset.target_name}")
    source_spec = _first_existing(asset.source_spec_candidates)

    skill_meta, skill_sections = _parse_markdown(source_skill, old_style=True)
    spec_meta: dict[str, Any] = {}
    spec_sections: dict[str, str] = {}
    if source_spec is not None and source_spec.exists():
        spec_meta, spec_sections = _parse_markdown(source_spec, old_style=True)
        if not spec_sections:
            text = source_spec.read_text(encoding="utf-8")
            spec_sections = {"detailed rules": _strip_frontmatter(text)}

    target_dir = asset.target_dir
    references_dir = target_dir / "references"
    assets_dir = target_dir / "assets"
    references_dir.mkdir(parents=True, exist_ok=True)
    assets_dir.mkdir(parents=True, exist_ok=True)

    (target_dir / "SKILL.md").write_text(
        _build_skill_markdown(asset, skill_meta, skill_sections, spec_sections),
        encoding="utf-8",
    )
    (references_dir / "spec.md").write_text(
        _build_spec_markdown(asset, skill_sections, source_spec, spec_meta, spec_sections),
        encoding="utf-8",
    )


def _remove_obsolete_tree() -> None:
    for relative in (
        "casual_chat",
        "clarify",
        "general_qa",
        "capabilities/education/education",
    ):
        path = PROMPT_ROOT / relative
        if path.exists():
            shutil.rmtree(path)


def build_sources() -> list[SourceAsset]:
    capability_dir = PROMPT_ROOT / "capabilities"
    component_dir = PROMPT_ROOT / "components"

    def skill_path(*parts: str) -> Path:
        return PROMPT_ROOT.joinpath(*parts)

    sources: list[SourceAsset] = [
        SourceAsset(
            target_kind="capability",
            target_name="general",
            target_dir=capability_dir / "general",
            source_skill_candidates=(skill_path("general_qa", "SKILL.md"),),
            source_spec_candidates=(skill_path("general_qa", "references", "spec.md"),),
            display_name="通用能力",
        ),
        SourceAsset(
            target_kind="capability",
            target_name="education",
            target_dir=capability_dir / "education",
            source_skill_candidates=(
                skill_path("education", "SKILL.md"),
                skill_path("capabilities", "education", "education", "SKILL.md"),
            ),
            source_spec_candidates=(
                skill_path("education", "references", "spec.md"),
                skill_path("capabilities", "education", "education", "references", "spec.md"),
            ),
            display_name="教育能力",
        ),
    ]

    for task_name, old_branch, old_leaf in (
        ("compare", "general_qa", "compare"),
        ("confirm", "general_qa", "confirm"),
        ("fact", "general_qa", "fact"),
        ("howto", "general_qa", "howto"),
        ("reasoned", "general_qa", "reasoned"),
        ("troubleshoot", "general_qa", "troubleshoot"),
        ("visual", "general_qa", "visual"),
        ("backchannel", "casual_chat", "backchannel"),
        ("companion", "casual_chat", "companion"),
        ("humor", "casual_chat", "humor"),
        ("praise", "casual_chat", "praise"),
        ("reaction", "casual_chat", "reaction"),
        ("smalltalk", "casual_chat", "smalltalk"),
        ("clarify-answer-mode", "clarify", "answer_mode"),
        ("clarify-focus", "clarify", "focus"),
        ("clarify-missing-material", "clarify", "missing_material"),
        ("clarify-missing-reference", "clarify", "missing_reference"),
        ("clarify-scene", "clarify", "scene"),
        ("clarify-subject", "clarify", "subject"),
    ):
        sources.append(
            SourceAsset(
                target_kind="task",
                target_name=task_name,
                target_dir=component_dir / "task" / task_name,
                source_skill_candidates=(
                    skill_path(old_branch, "modes", old_leaf, "SKILL.md"),
                    skill_path("components", "task", task_name, "SKILL.md"),
                ),
                source_spec_candidates=(
                    skill_path(old_branch, "modes", old_leaf, "references", "spec.md"),
                    skill_path("components", "task", task_name, "references", "spec.md"),
                ),
                display_name=task_name,
            )
        )

    for task_name in ("answer", "check", "drill", "explain", "qa", "solve"):
        sources.append(
            SourceAsset(
                target_kind="task",
                target_name=task_name,
                target_dir=component_dir / "task" / task_name,
                source_skill_candidates=(
                    skill_path("education", "modules", task_name, "SKILL.md"),
                    skill_path("capabilities", "education", "education", "modules", task_name, "SKILL.md"),
                ),
                source_spec_candidates=(
                    skill_path("education", "modules", task_name, "references", "spec.md"),
                    skill_path("capabilities", "education", "education", "modules", task_name, "references", "spec.md"),
                ),
                display_name=task_name,
            )
        )

    for target_name, old_leaf in (
        ("chinese", "chinese"),
        ("cs", "cs"),
        ("english", "english"),
        ("math", "math"),
        ("general-knowledge", "general"),
    ):
        sources.append(
            SourceAsset(
                target_kind="knowledge",
                target_name=target_name,
                target_dir=component_dir / "knowledge" / target_name,
                source_skill_candidates=(
                    skill_path("education", "subjects", old_leaf, "SKILL.md"),
                    skill_path("capabilities", "education", "education", "subjects", old_leaf, "SKILL.md"),
                ),
                source_spec_candidates=(
                    skill_path("education", "subjects", old_leaf, "references", "spec.md"),
                    skill_path("capabilities", "education", "education", "subjects", old_leaf, "references", "spec.md"),
                ),
                display_name=target_name,
            )
        )

    for target_name, old_leaf in (
        ("direct", "direct"),
        ("explain-careful", "explain_careful"),
        ("hint-only", "hint_only"),
        ("step-by-step", "step_by_step"),
    ):
        sources.append(
            SourceAsset(
                target_kind="method",
                target_name=target_name,
                target_dir=component_dir / "method" / target_name,
                source_skill_candidates=(
                    skill_path("education", "pedagogies", old_leaf, "SKILL.md"),
                    skill_path("capabilities", "education", "education", "pedagogies", old_leaf, "SKILL.md"),
                ),
                source_spec_candidates=(
                    skill_path("education", "pedagogies", old_leaf, "references", "spec.md"),
                    skill_path("capabilities", "education", "education", "pedagogies", old_leaf, "references", "spec.md"),
                ),
                display_name=target_name,
            )
        )

    return sources


def main() -> None:
    (PROMPT_ROOT / "capabilities").mkdir(parents=True, exist_ok=True)
    (PROMPT_ROOT / "components" / "task").mkdir(parents=True, exist_ok=True)
    (PROMPT_ROOT / "components" / "knowledge").mkdir(parents=True, exist_ok=True)
    (PROMPT_ROOT / "components" / "method").mkdir(parents=True, exist_ok=True)
    (PROMPT_ROOT / "components" / "audience").mkdir(parents=True, exist_ok=True)

    for asset in build_sources():
        _write_skill(asset)

    _remove_obsolete_tree()


if __name__ == "__main__":
    main()
