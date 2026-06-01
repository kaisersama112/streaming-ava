"""Prompt Skill 路径注册表。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath


@dataclass(frozen=True)
class PromptSkillLocation:
    """单个 Skill 的目录入口。"""

    skill_file: str


class PromptSkillRegistry:
    """统一管理 Prompt Skill 的目录布局。"""

    def branch(self, branch: str) -> PromptSkillLocation:
        return PromptSkillLocation(skill_file=f"{branch}/SKILL.md")

    def mode(self, branch: str, mode: str) -> PromptSkillLocation:
        return PromptSkillLocation(skill_file=f"{branch}/modes/{mode}/SKILL.md")

    def education_branch(self) -> PromptSkillLocation:
        return PromptSkillLocation(skill_file="education/SKILL.md")

    def education_module(self, module: str) -> PromptSkillLocation:
        return PromptSkillLocation(skill_file=f"education/modules/{module}/SKILL.md")

    def education_subject(self, subject: str) -> PromptSkillLocation:
        return PromptSkillLocation(skill_file=f"education/subjects/{subject}/SKILL.md")

    def education_pedagogy(self, pedagogy: str) -> PromptSkillLocation:
        return PromptSkillLocation(skill_file=f"education/pedagogies/{pedagogy}/SKILL.md")

    @staticmethod
    def resolve_relative(base_file: str, relative_path: str) -> str:
        """按 POSIX 路径规则解析 Skill 内部相对引用。"""
        return str((PurePosixPath(base_file).parent / relative_path).as_posix())
