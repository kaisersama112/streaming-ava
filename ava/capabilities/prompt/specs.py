"""Prompt Skill 正式数据结构。

当前模块只保留统一合同中的正式对象：
- `Skill`
- `PromptPackage`

不再保留按 kind 拆散的多套 Spec 类型。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


SkillKind = Literal["capability", "task", "knowledge", "method", "audience"]


@dataclass(frozen=True)
class Skill:
    """统一 Skill 对象。

    字段说明：
    - `name`：全局唯一的 Skill 名称
    - `description`：用于检索、触发与说明的简述
    - `kind`：Skill 类型
    - `version`：Skill 版本号
    - `load_policy`：加载策略
    - `purpose`：Skill 目标说明
    - `instructions`：Skill 执行规则文本
    - `references`：Skill 引用资源路径
    - `assets`：Skill 资源路径
    - `examples`：Skill 触发示例文本
    - `source_file`：当前 Skill 入口文件的仓库相对路径
    - `raw`：保留原始解析结果，便于调试
    """

    name: str
    description: str
    kind: SkillKind
    version: str
    load_policy: str
    purpose: str
    instructions: str
    references: tuple[str, ...] = ()
    assets: tuple[str, ...] = ()
    examples: tuple[str, ...] = ()
    source_file: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    def to_metadata(self) -> dict[str, Any]:
        """导出稳定元数据。"""
        return {
            "name": self.name,
            "description": self.description,
            "kind": self.kind,
            "version": self.version,
            "load_policy": self.load_policy,
            "purpose": self.purpose,
            "instructions": self.instructions,
            "references": list(self.references),
            "assets": list(self.assets),
            "examples": list(self.examples),
            "source_file": self.source_file,
        }


@dataclass(frozen=True)
class PromptPackage:
    """Prompt 组合结果。

    运行时只消费这个统一对象，不再消费多类 Prompt Spec。
    """

    capability: Skill
    skills: tuple[Skill, ...]
    references: tuple[str, ...]
    assets: tuple[str, ...]
    prompt: str

    def skill_names(self, kind: SkillKind | None = None) -> list[str]:
        """返回当前 PromptPackage 中的 Skill 名称列表。"""
        selected = self.skills
        if kind is not None:
            selected = tuple(skill for skill in self.skills if skill.kind == kind)
        return [skill.name for skill in selected]

    def primary_skill_name(self, kind: SkillKind) -> str:
        """返回某类 Skill 的首个名称；不存在时返回空字符串。"""
        for skill in self.skills:
            if skill.kind == kind:
                return skill.name
        return ""

    def runtime_profile(self) -> dict[str, Any]:
        """导出运行时稳定使用的 Prompt 组合视图。"""
        return {
            "capability": self.capability.name,
            "task": self.primary_skill_name("task"),
            "knowledge": self.primary_skill_name("knowledge"),
            "method": self.primary_skill_name("method"),
            "audience": self.primary_skill_name("audience"),
            "skills": self.skill_names(),
        }

    def to_metadata(self) -> dict[str, Any]:
        """导出稳定元数据。"""
        profile = self.runtime_profile()
        return {
            "capability": profile["capability"],
            "task": profile["task"],
            "knowledge": profile["knowledge"],
            "method": profile["method"],
            "audience": profile["audience"],
            "skills": profile["skills"],
            "references": list(self.references),
            "assets": list(self.assets),
            "prompt_length": len(self.prompt or ""),
        }
