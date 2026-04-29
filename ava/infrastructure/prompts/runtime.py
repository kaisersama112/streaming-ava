"""Prompt runtimes built on structured markdown assets."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

import yaml

from .loader import MarkdownAsset, PromptCenter


@dataclass(frozen=True)
class PluginSpec:
    asset_id: str
    version: int
    name: str
    purpose: str
    rules: tuple[str, ...] = ()
    raw: dict[str, Any] | None = None


@dataclass(frozen=True)
class ModuleSpec:
    asset_id: str
    version: int
    name: str
    goal: str
    applies_to: tuple[str, ...] = ()
    response_structure: tuple[str, ...] = ()
    global_rules: tuple[str, ...] = ()
    interaction_policy: tuple[str, ...] = ()
    output_defaults: dict[str, Any] | None = None
    instructions: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()
    supports_modalities: tuple[str, ...] = ()
    supports_question_kinds: tuple[str, ...] = ()
    raw: dict[str, Any] | None = None


@dataclass(frozen=True)
class SubjectSpec:
    asset_id: str
    version: int
    name: str
    focus: tuple[str, ...] = ()
    explanation_strategy: tuple[str, ...] = ()
    common_mistakes: tuple[str, ...] = ()
    evidence_preference: tuple[str, ...] = ()
    ui_hints: dict[str, Any] | None = None
    instructions: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()
    supports_artifacts: tuple[str, ...] = ()
    raw: dict[str, Any] | None = None


@dataclass(frozen=True)
class StyleSpec:
    asset_id: str
    version: int
    name: str
    tone: str
    constraints: tuple[str, ...] = ()
    output_adjustments: dict[str, Any] | None = None
    instructions: tuple[str, ...] = ()
    style_traits: tuple[str, ...] = ()
    raw: dict[str, Any] | None = None


@dataclass(frozen=True)
class ModeSpec:
    asset_id: str
    version: int
    name: str
    description: str
    delivery_mode: str
    ui_mode: str
    response_shape: str
    objective: str
    instructions: tuple[str, ...] = ()
    interaction_rules: tuple[str, ...] = ()
    examples: tuple[str, ...] = ()
    response_contract: dict[str, Any] | None = None
    speech_policy: dict[str, Any] | None = None
    ui_policy: dict[str, Any] | None = None
    raw: dict[str, Any] | None = None


def _tupled(items: list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
    return tuple(str(item).strip() for item in (items or []) if str(item).strip())


def _module_defaults(asset_id: str) -> dict[str, tuple[str, ...]]:
    defaults = {
        "solve": {
            "capabilities": ("problem_solving", "multi_step_decomposition", "method_guidance"),
            "supports_modalities": ("text", "image"),
            "supports_question_kinds": ("multi_step_problem", "diagram_parse"),
        },
        "check": {
            "capabilities": ("solution_check", "error_localization", "short_feedback"),
            "supports_modalities": ("text", "image"),
            "supports_question_kinds": ("solution_check", "error_diagnosis"),
        },
        "explain": {
            "capabilities": ("contextual_explanation", "concept_grounding", "step_explanation"),
            "supports_modalities": ("text", "image", "video", "audio"),
            "supports_question_kinds": ("contextual_problem_solving", "step_explanation", "concept_explain"),
        },
        "drill": {
            "capabilities": ("exercise_generation", "difficulty_control", "coverage_planning"),
            "supports_modalities": ("text", "image"),
            "supports_question_kinds": ("exercise_generation",),
        },
        "answer": {
            "capabilities": ("answer_validation", "short_justification", "option_analysis"),
            "supports_modalities": ("text", "image"),
            "supports_question_kinds": ("option_select", "option_verify"),
        },
        "qa": {
            "capabilities": ("concept_explanation", "compare_explanation", "causal_explanation"),
            "supports_modalities": ("text", "image", "audio"),
            "supports_question_kinds": ("concept_explain", "compare", "why_reason"),
        },
    }
    return defaults.get(asset_id, {})


def _subject_defaults(asset_id: str) -> dict[str, tuple[str, ...]]:
    defaults = {
        "math": {
            "capabilities": ("formula_reasoning", "condition_check"),
            "supports_artifacts": ("image",),
        },
        "english": {
            "capabilities": ("grammar_explanation", "language_compare"),
            "supports_artifacts": ("image", "audio"),
        },
        "chinese": {
            "capabilities": ("text_explanation", "writing_feedback"),
            "supports_artifacts": ("image", "file"),
        },
        "cs": {
            "capabilities": ("error_diagnosis", "logic_bug_analysis", "diagram_parse"),
            "supports_artifacts": ("image", "file"),
        },
        "physics": {
            "capabilities": ("experiment_reasoning", "diagram_parse"),
            "supports_artifacts": ("image", "video"),
        },
        "history": {
            "capabilities": ("timeline_reasoning", "source_classification", "historical_context"),
            "supports_artifacts": ("image", "video", "file"),
        },
        "general": {
            "capabilities": ("general_explanation",),
            "supports_artifacts": ("image", "audio", "file"),
        },
    }
    return defaults.get(asset_id, {})


def _style_defaults(asset_id: str) -> tuple[str, ...]:
    defaults = {
        "direct": ("direct_answer", "concise"),
        "explain_careful": ("careful", "structured"),
        "hint_only": ("guided", "interactive"),
        "step_by_step": ("structured", "guided"),
    }
    return defaults.get(asset_id, ())


def _match_value(actual: Any, expected: Any) -> bool:
    if isinstance(expected, dict):
        if "equals" in expected:
            return _match_value(actual, expected["equals"])
        if "any_of" in expected:
            return any(_match_value(actual, item) for item in expected.get("any_of", []))
        if "all_of" in expected:
            return all(_match_value(actual, item) for item in expected.get("all_of", []))
        if "not" in expected:
            return not _match_value(actual, expected["not"])
        if "truthy" in expected:
            return bool(actual) is bool(expected["truthy"])
        if "contains_any" in expected:
            wanted = [str(item) for item in expected.get("contains_any", [])]
            if isinstance(actual, str):
                return any(item in actual for item in wanted)
            if isinstance(actual, (list, tuple, set)):
                actual_values = {str(item) for item in actual}
                return bool(actual_values.intersection(wanted))
            return False
    if isinstance(expected, (list, tuple, set)):
        if isinstance(actual, (list, tuple, set)):
            return bool({str(item) for item in actual}.intersection({str(item) for item in expected}))
        return actual in expected
    if isinstance(actual, (list, tuple, set)):
        return expected in actual
    return actual == expected


def _require_meta(asset: MarkdownAsset, key: str) -> Any:
    value = asset.meta.get(key)
    if value in (None, ""):
        raise ValueError(f"{asset.path}: missing required frontmatter key '{key}'")
    return value


def _require_section(asset: MarkdownAsset, name: str) -> str:
    value = asset.sections.get(name.lower(), "").strip()
    if not value:
        raise ValueError(f"{asset.path}: missing required section '{name}'")
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
            raise ValueError(f"Expected markdown mapping line in `key = value` form, got: {raw_line!r}")
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
        raise ValueError("Expected markdown rule table with header and separator rows")

    headers = [_normalize_rule_table_header(cell) for cell in _split_markdown_table_row(lines[0])]
    if not any(headers):
        raise ValueError("Expected markdown rule table header row")
    if not _is_markdown_table_separator(lines[1]):
        raise ValueError("Expected markdown rule table separator row")

    select_index = next((index for index, key in enumerate(headers) if key in _RULE_TABLE_SELECT_KEYS), None)
    if select_index is None:
        raise ValueError("Expected markdown rule table to contain a `select` column")

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
            raise ValueError(f"Expected markdown rule line starting with `if`, got: {raw_line!r}")
        condition_part, sep, select_part = stripped.partition("->")
        if not sep:
            raise ValueError(f"Expected markdown rule line containing `->`, got: {raw_line!r}")
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
            raise ValueError(f"Unsupported markdown rule clause: {clause!r}")
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
        raise ValueError("Expected mapping-like config block")
    return payload


def _parse_plugin(asset: MarkdownAsset) -> PluginSpec:
    if asset.meta.get("type") != "plugin":
        raise ValueError(f"{asset.path}: expected type=plugin")
    raw = {
        "meta": dict(asset.meta),
        "purpose": _require_section(asset, "Purpose"),
        "rules": _parse_list_block(_require_section(asset, "Rules")),
    }
    return PluginSpec(
        asset_id=str(_require_meta(asset, "id")),
        version=int(asset.meta.get("version", 1)),
        name=_require_section(asset, "Name"),
        purpose=raw["purpose"],
        rules=_tupled(raw["rules"]),
        raw=raw,
    )


def _parse_module(asset: MarkdownAsset) -> ModuleSpec:
    if asset.meta.get("type") != "module":
        raise ValueError(f"{asset.path}: expected type=module")
    defaults = _module_defaults(str(_require_meta(asset, "id")))
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
        capabilities=_tupled(asset.meta.get("capabilities") or defaults.get("capabilities")),
        supports_modalities=_tupled(asset.meta.get("supports_modalities") or defaults.get("supports_modalities")),
        supports_question_kinds=_tupled(asset.meta.get("supports_question_kinds") or defaults.get("supports_question_kinds")),
        raw=raw,
    )


def _parse_subject(asset: MarkdownAsset) -> SubjectSpec:
    if asset.meta.get("type") != "subject":
        raise ValueError(f"{asset.path}: expected type=subject")
    defaults = _subject_defaults(str(_require_meta(asset, "id")))
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
        capabilities=_tupled(asset.meta.get("capabilities") or defaults.get("capabilities")),
        supports_artifacts=_tupled(asset.meta.get("supports_artifacts") or defaults.get("supports_artifacts")),
        raw=raw,
    )


def _parse_style(asset: MarkdownAsset) -> StyleSpec:
    if asset.meta.get("type") != "style":
        raise ValueError(f"{asset.path}: expected type=style")
    asset_id = str(_require_meta(asset, "id"))
    raw = {
        "meta": dict(asset.meta),
        "tone": _require_section(asset, "Tone"),
        "constraints": _parse_list_block(_require_section(asset, "Constraints")),
        "output_adjustments": _parse_mapping_block(_require_section(asset, "Output Adjustments")),
        "instructions": _parse_list_block(_require_section(asset, "Instructions")),
    }
    return StyleSpec(
        asset_id=asset_id,
        version=int(asset.meta.get("version", 1)),
        name=_require_section(asset, "Name"),
        tone=raw["tone"],
        constraints=_tupled(raw["constraints"]),
        output_adjustments=dict(raw["output_adjustments"]),
        instructions=_tupled(raw["instructions"]),
        style_traits=_tupled(asset.meta.get("style_traits") or _style_defaults(asset_id)),
        raw=raw,
    )


def _parse_mode(asset: MarkdownAsset) -> ModeSpec:
    if asset.meta.get("type") != "mode":
        raise ValueError(f"{asset.path}: expected type=mode")
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


class SimpleBranchPromptRuntime:
    def __init__(self, prompt_center: PromptCenter):
        self.prompt_center = prompt_center
        self._plugin_cache: dict[str, PluginSpec] = {}
        self._mode_cache: dict[tuple[str, str], ModeSpec] = {}

    def load_plugin(self, branch: str) -> PluginSpec:
        if branch in self._plugin_cache:
            return self._plugin_cache[branch]
        plugin = _parse_plugin(self.prompt_center.load_markdown_asset(f"plugins/{branch}/plugin.md"))
        self._plugin_cache[branch] = plugin
        return plugin

    def load_mode(self, branch: str, mode: str) -> ModeSpec:
        cache_key = (branch, mode)
        if cache_key in self._mode_cache:
            return self._mode_cache[cache_key]
        mode_spec = _parse_mode(self.prompt_center.load_markdown_asset(f"plugins/{branch}/modes/{mode}.md"))
        self._mode_cache[cache_key] = mode_spec
        return mode_spec


class ComposedPromptRuntime:
    def __init__(self, prompt_center: PromptCenter):
        self.prompt_center = prompt_center
        self._yaml_cache: dict[str, Any] = {}
        self._rule_cache: dict[tuple[str, str], dict[str, Any]] = {}
        self._plugin_cache: dict[str, PluginSpec] = {}
        self._module_cache: dict[str, ModuleSpec] = {}
        self._subject_cache: dict[tuple[str, str], SubjectSpec] = {}
        self._style_cache: dict[tuple[str, str], StyleSpec] = {}

    def _module_root(self) -> Path:
        return Path(self.prompt_center.config.prompt_dir) / "plugins" / "education" / "modules"

    def _load_yaml(self, relative_path: str) -> dict[str, Any]:
        if relative_path in self._yaml_cache:
            return self._yaml_cache[relative_path]
        payload = self.prompt_center.load_yaml(relative_path) or {}
        self._yaml_cache[relative_path] = payload
        return payload

    def _load_rules_payload(
        self,
        markdown_relative_path: str,
        section_name: str,
        yaml_relative_path: str | None = None,
    ) -> tuple[dict[str, Any], str]:
        cache_key = (markdown_relative_path, section_name.lower())
        if cache_key in self._rule_cache:
            return self._rule_cache[cache_key], f"{markdown_relative_path}#{section_name}"

        try:
            asset = self.prompt_center.load_markdown_asset(markdown_relative_path)
            raw_section = asset.sections.get(section_name.lower(), "").strip()
            if raw_section:
                payload = _parse_mapping_block(raw_section)
                self._rule_cache[cache_key] = payload
                return payload, f"{markdown_relative_path}#{section_name}"
        except FileNotFoundError:
            pass

        if not yaml_relative_path:
            raise FileNotFoundError(f"Missing selector rules in markdown section {section_name}: {markdown_relative_path}")

        return self._load_yaml(yaml_relative_path), yaml_relative_path

    def _select_id_with_trace(
        self,
        payload: dict[str, Any],
        rule_path: str,
        features: dict[str, Any],
        default: str,
    ) -> tuple[str, dict[str, Any]]:
        rules = payload.get("rules", []) or []
        for index, rule in enumerate(rules):
            conditions = rule.get("when", {}) or {}
            if all(_match_value(features.get(key), expected) for key, expected in conditions.items()):
                selected = str(rule.get("select", "")).strip()
                if selected:
                    return selected, {
                        "rule_path": rule_path,
                        "matched_rule_index": index,
                        "matched_when": dict(conditions),
                        "used_default": False,
                        "default_value": default,
                    }
        return default, {
            "rule_path": rule_path,
            "matched_rule_index": None,
            "matched_when": {},
            "used_default": True,
            "default_value": default,
        }

    def load_plugin(self) -> PluginSpec:
        if "education" in self._plugin_cache:
            return self._plugin_cache["education"]
        plugin = _parse_plugin(self.prompt_center.load_markdown_asset("plugins/education/plugin.md"))
        self._plugin_cache["education"] = plugin
        return plugin

    def list_module_ids(self) -> tuple[str, ...]:
        root = self._module_root()
        if not root.exists():
            return ()
        return tuple(sorted(path.name for path in root.iterdir() if path.is_dir()))

    def list_subject_ids(self, module: str) -> tuple[str, ...]:
        subjects: set[str] = set()
        for module_name in (module, "solve"):
            root = self._module_root() / module_name / "subjects"
            if not root.exists():
                continue
            subjects.update(path.stem for path in root.iterdir() if path.is_file() and path.suffix == ".md")
        return tuple(sorted(subjects))

    def list_style_ids(self, module: str) -> tuple[str, ...]:
        styles: set[str] = set()
        for module_name in (module, "solve"):
            root = self._module_root() / module_name / "styles"
            if not root.exists():
                continue
            styles.update(path.stem for path in root.iterdir() if path.is_file() and path.suffix == ".md")
        return tuple(sorted(styles))

    def select_module_with_trace(self, features: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        payload, rule_path = self._load_rules_payload(
            "plugins/education/plugin.md",
            "Module Selection Rules",
            "plugins/education/selectors/module_rules.yaml",
        )
        return self._select_id_with_trace(payload, rule_path, features, "qa")

    def select_subject_with_trace(self, module: str, features: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        payload, rule_path = self._load_rules_payload(
            f"plugins/education/modules/{module}/module.md",
            "Subject Selection Rules",
            f"plugins/education/modules/{module}/selectors/subject_rules.yaml",
        )
        return self._select_id_with_trace(payload, rule_path, features, "general")

    def select_style_with_trace(self, module: str, features: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        payload, rule_path = self._load_rules_payload(
            f"plugins/education/modules/{module}/module.md",
            "Style Selection Rules",
            f"plugins/education/modules/{module}/selectors/style_rules.yaml",
        )
        return self._select_id_with_trace(payload, rule_path, features, "step_by_step")

    def load_module(self, module: str) -> ModuleSpec:
        if module in self._module_cache:
            return self._module_cache[module]
        module_spec = _parse_module(
            self.prompt_center.load_markdown_asset(f"plugins/education/modules/{module}/module.md")
        )
        self._module_cache[module] = module_spec
        return module_spec

    def load_subject(self, module: str, subject: str) -> SubjectSpec:
        cache_key = (module, subject)
        if cache_key in self._subject_cache:
            return self._subject_cache[cache_key]
        relative_path = f"plugins/education/modules/{module}/subjects/{subject}.md"
        try:
            asset = self.prompt_center.load_markdown_asset(relative_path)
        except FileNotFoundError:
            asset = self.prompt_center.load_markdown_asset(f"plugins/education/modules/solve/subjects/{subject}.md")
        subject_spec = _parse_subject(asset)
        self._subject_cache[cache_key] = subject_spec
        return subject_spec

    def load_style(self, module: str, style: str) -> StyleSpec:
        cache_key = (module, style)
        if cache_key in self._style_cache:
            return self._style_cache[cache_key]
        relative_path = f"plugins/education/modules/{module}/styles/{style}.md"
        try:
            asset = self.prompt_center.load_markdown_asset(relative_path)
        except FileNotFoundError:
            asset = self.prompt_center.load_markdown_asset(f"plugins/education/modules/solve/styles/{style}.md")
        style_spec = _parse_style(asset)
        self._style_cache[cache_key] = style_spec
        return style_spec
