"""Prompt Skill 路径注册表。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from pathlib import PurePosixPath


@dataclass(frozen=True)
class PromptSkillLocation:
    """单个 Skill 的路径描述。"""

    skill_file: str


class PromptSkillRegistry:
    """统一 Skill 目录注册表。"""

    _KIND_DIRECTORIES = {
        "capability": "capabilities",
        "task": "components/task",
        "knowledge": "components/knowledge",
        "method": "components/method",
        "audience": "components/audience",
    }

    def capability(self, name: str) -> PromptSkillLocation:
        return PromptSkillLocation(skill_file=f"capabilities/{name}/SKILL.md")

    def task(self, name: str) -> PromptSkillLocation:
        return PromptSkillLocation(skill_file=f"components/task/{name}/SKILL.md")

    def knowledge(self, name: str) -> PromptSkillLocation:
        return PromptSkillLocation(skill_file=f"components/knowledge/{name}/SKILL.md")

    def method(self, name: str) -> PromptSkillLocation:
        return PromptSkillLocation(skill_file=f"components/method/{name}/SKILL.md")

    def audience(self, name: str) -> PromptSkillLocation:
        return PromptSkillLocation(skill_file=f"components/audience/{name}/SKILL.md")

    def kind_directory(self, kind: str) -> str:
        """返回某类 Skill 的目录根路径。"""
        if kind not in self._KIND_DIRECTORIES:
            raise KeyError(f"未知 Skill kind: {kind}")
        return self._KIND_DIRECTORIES[kind]

    def list_names(self, *, prompt_root: Path, kind: str) -> list[str]:
        """列出某类 Skill 的全部名称。"""
        directory = prompt_root / self.kind_directory(kind)
        if not directory.exists() or not directory.is_dir():
            return []
        names: list[str] = []
        for item in directory.iterdir():
            if item.is_dir() and (item / "SKILL.md").exists():
                names.append(item.name)
        return sorted(names)

    @staticmethod
    def resolve_relative(base_file: str, relative_path: str) -> str:
        """按 POSIX 规则解析 Skill 内部相对路径。"""
        return str((PurePosixPath(base_file).parent / relative_path).as_posix())
