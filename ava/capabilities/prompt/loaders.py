"""Prompt Skill 业务加载器。"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import TYPE_CHECKING

from .registry import PromptSkillRegistry
from .specs import PromptPackage, Skill

if TYPE_CHECKING:
    from .prompt_loader import PromptCenter


@dataclass(frozen=True)
class PromptSkillSet:
    """一次组合中用到的 Skill 集合。"""

    capability: Skill
    skills: tuple[Skill, ...]


class PromptSkillLoader:
    """统一 Skill 加载器。"""

    def __init__(self, prompt_center: "PromptCenter") -> None:
        self.prompt_center = prompt_center
        self.registry = PromptSkillRegistry()
        self._cache: dict[str, Skill] = {}

    def load_capability(self, name: str) -> Skill:
        return self._load(self.registry.capability(name).skill_file)

    def load_task(self, name: str) -> Skill:
        return self._load(self.registry.task(name).skill_file)

    def load_knowledge(self, name: str) -> Skill:
        return self._load(self.registry.knowledge(name).skill_file)

    def load_method(self, name: str) -> Skill:
        return self._load(self.registry.method(name).skill_file)

    def load_audience(self, name: str) -> Skill:
        return self._load(self.registry.audience(name).skill_file)

    def list_capability_names(self) -> list[str]:
        return self.registry.list_names(prompt_root=self.prompt_center.config.prompt_dir, kind="capability")

    def list_task_names(self) -> list[str]:
        return self.registry.list_names(prompt_root=self.prompt_center.config.prompt_dir, kind="task")

    def list_knowledge_names(self) -> list[str]:
        return self.registry.list_names(prompt_root=self.prompt_center.config.prompt_dir, kind="knowledge")

    def list_method_names(self) -> list[str]:
        return self.registry.list_names(prompt_root=self.prompt_center.config.prompt_dir, kind="method")

    def list_audience_names(self) -> list[str]:
        return self.registry.list_names(prompt_root=self.prompt_center.config.prompt_dir, kind="audience")

    def _load(self, skill_file: str) -> Skill:
        if skill_file in self._cache:
            return self._cache[skill_file]
        skill = self.prompt_center.load_skill(skill_file)
        self._cache[skill_file] = skill
        return skill

    def load_reference_texts(self, skill: Skill) -> list[tuple[str, str]]:
        """读取当前 Skill 引用的全部规范文本。"""
        texts: list[tuple[str, str]] = []
        for relative_path in skill.references:

            resolved = self.prompt_center.registry.resolve_relative(skill.source_file, relative_path)
            texts.append((resolved, self.prompt_center.read_text(resolved).strip()))
        return texts

    def get_reference_setting(self, skill: Skill, key: str) -> str:
        """从 Skill 的 references 文本中抽取形如 `- key = value` 的设置。"""
        pattern = re.compile(rf"(?mi)^\\s*-\\s*{re.escape(key)}\\s*=\\s*(.+?)\\s*$")
        for _, text in self.load_reference_texts(skill):
            matched = pattern.search(text)
            if matched:
                return str(matched.group(1) or "").strip()
        return ""

    @staticmethod
    def build_package(*, capability: Skill, skills: list[Skill], prompt: str) -> PromptPackage:
        """根据已装配的 Skill 列表构造 PromptPackage。"""
        references: list[str] = []
        assets: list[str] = []
        for skill in (capability, *skills):
            references.extend(list(skill.references))
            assets.extend(list(skill.assets))
        dedup_references = tuple(dict.fromkeys(references))
        dedup_assets = tuple(dict.fromkeys(assets))
        ordered_skills = tuple([capability, *skills])
        return PromptPackage(
            capability=capability,
            skills=ordered_skills,
            references=dedup_references,
            assets=dedup_assets,
            prompt=prompt.strip(),
        )
