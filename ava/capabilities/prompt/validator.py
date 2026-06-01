"""Prompt Skill 校验器。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .prompt_loader import PromptCenter
from .specs import Skill


@dataclass(frozen=True)
class ValidationIssue:
    """单条校验问题。"""

    path: str
    message: str


class SkillValidator:
    """统一 Skill 校验器。"""

    def __init__(self, prompt_center: PromptCenter) -> None:
        self.prompt_center = prompt_center

    def validate_all(self) -> list[ValidationIssue]:
        """扫描并校验全部 Skill。"""
        issues: list[ValidationIssue] = []
        names: dict[str, str] = {}
        for skill_file in self._skill_files():
            try:
                skill = self.prompt_center.load_skill(skill_file)
            except Exception as exc:
                issues.append(ValidationIssue(path=skill_file, message=str(exc)))
                continue
            issues.extend(self._validate_skill(skill_file, skill))
            existing = names.get(skill.name)
            if existing is not None:
                issues.append(ValidationIssue(path=skill_file, message=f"Skill name 重复：{skill.name}，首次出现于 {existing}"))
            else:
                names[skill.name] = skill_file
        return issues

    def _validate_skill(self, skill_file: str, skill: Skill) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        base_dir = Path(skill_file).parent
        for relative_path in skill.references:
            path = self.prompt_center._resolve(str(base_dir / relative_path))
            if not path.exists():
                issues.append(ValidationIssue(path=skill_file, message=f"references 文件不存在：{relative_path}"))
        for relative_path in skill.assets:
            path = self.prompt_center._resolve(str(base_dir / relative_path))
            if not path.exists():
                issues.append(ValidationIssue(path=skill_file, message=f"assets 文件不存在：{relative_path}"))
        return issues

    def _skill_files(self) -> list[str]:
        root = self.prompt_center.config.prompt_dir
        files: list[str] = []
        for path in root.rglob("SKILL.md"):
            relative = path.relative_to(root).as_posix()
            if relative.startswith("core/"):
                continue
            files.append(relative)
        return sorted(files)
