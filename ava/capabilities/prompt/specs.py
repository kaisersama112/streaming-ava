"""Prompt 资产的正式结构定义。

该模块只定义稳定的数据结构，不承担任何运行时职责。

当前统一分为两层：
1. `PromptSkillCard`
   - 对应每个技能目录下的 `SKILL.md`
   - 只承载触发摘要、加载策略、引用入口等轻量信息
2. 结构化正式资产
   - 对应 `references/spec.md`
   - 承载系统提示真正依赖的稳定规则与结构字段
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


PromptAssetType = Literal["branch", "mode", "module", "subject", "pedagogy"]


@dataclass(frozen=True)
class PromptReferenceEntry:
    """Skill 引用资源条目。"""

    path: str
    purpose: str = ""
    when: str = ""


@dataclass(frozen=True)
class PromptSkillCard:
    """Skill 入口卡片。

    这是渐进披露的前两层信息：
    - frontmatter：名称、描述、资产类型、正式引用入口
    - SKILL 正文：何时触发、何时继续读取 `references/`
    """

    name: str
    description: str
    asset_id: str
    asset_type: PromptAssetType
    version: int
    entry_reference: str
    title: str = ""
    trigger_items: tuple[str, ...] = ()
    procedure_items: tuple[str, ...] = ()
    reference_items: tuple[str, ...] = ()
    decision_notes: tuple[str, ...] = ()
    pattern: str = ""
    load_policy: str = ""
    references: tuple[PromptReferenceEntry, ...] = ()
    raw: dict[str, Any] | None = None


@dataclass(frozen=True)
class BranchSpec:
    """分支级资产。"""

    asset_id: str
    version: int
    name: str
    purpose: str
    rules: tuple[str, ...] = ()
    raw: dict[str, Any] | None = None


@dataclass(frozen=True)
class ModuleSpec:
    """教育模块资产。"""

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
    """教育学科资产。"""

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
class PedagogySpec:
    """教育教学法资产。"""

    asset_id: str
    version: int
    name: str
    tone: str
    constraints: tuple[str, ...] = ()
    output_adjustments: dict[str, Any] | None = None
    instructions: tuple[str, ...] = ()
    pedagogy_traits: tuple[str, ...] = ()
    raw: dict[str, Any] | None = None


@dataclass(frozen=True)
class ModeSpec:
    """通用分支模式资产。"""

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
