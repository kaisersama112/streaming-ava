"""Prompt 正式加载器。

该模块是 Prompt 资产的唯一业务化加载入口：
- `BranchPromptLoader`：加载通用分支与 mode
- `EducationPromptLoader`：加载教育分支、模块、学科、教学法
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Generic, TypeVar

from .registry import PromptSkillRegistry
from .specs import BranchSpec, ModeSpec, ModuleSpec, PedagogySpec, PromptSkillCard, SubjectSpec

if TYPE_CHECKING:
    from .prompt_loader import PromptCenter


PromptSpecType = TypeVar("PromptSpecType")


@dataclass(frozen=True)
class PromptSkillAsset(Generic[PromptSpecType]):
    """单个 Prompt Skill 的加载结果。"""

    skill: PromptSkillCard
    spec: PromptSpecType


@dataclass(frozen=True)
class EducationPromptAssets:
    """一轮教育回答实际使用到的正式提示资产集合。"""

    branch_skill: PromptSkillCard
    branch: BranchSpec
    module_skill: PromptSkillCard
    module: ModuleSpec
    subject_skill: PromptSkillCard
    subject: SubjectSpec
    pedagogy_skill: PromptSkillCard
    pedagogy: PedagogySpec


class BranchPromptLoader:
    """负责加载通用分支 Skill。"""

    def __init__(self, prompt_center: "PromptCenter") -> None:
        self.prompt_center = prompt_center
        self.registry = PromptSkillRegistry()
        self._branch_cache: dict[str, PromptSkillAsset[BranchSpec]] = {}
        self._mode_cache: dict[tuple[str, str], PromptSkillAsset[ModeSpec]] = {}

    def load_branch_asset(self, branch: str) -> PromptSkillAsset[BranchSpec]:
        """加载分支级资产。"""
        if branch in self._branch_cache:
            return self._branch_cache[branch]
        location = self.registry.branch(branch)
        card = self.prompt_center.load_skill_card(location.skill_file)
        asset = self.prompt_center.load_skill_reference_asset(location.skill_file, card.entry_reference)
        loaded = PromptSkillAsset(
            skill=card,
            spec=self.prompt_center.spec_parser.parse_branch(asset),
        )
        self._branch_cache[branch] = loaded
        return loaded

    def load_branch(self, branch: str) -> BranchSpec:
        """加载分支正式规范。"""
        return self.load_branch_asset(branch).spec

    def load_mode_asset(self, branch: str, mode: str) -> PromptSkillAsset[ModeSpec]:
        """加载通用分支下的 mode 资产。"""
        cache_key = (branch, mode)
        if cache_key in self._mode_cache:
            return self._mode_cache[cache_key]
        location = self.registry.mode(branch, mode)
        card = self.prompt_center.load_skill_card(location.skill_file)
        asset = self.prompt_center.load_skill_reference_asset(location.skill_file, card.entry_reference)
        loaded = PromptSkillAsset(
            skill=card,
            spec=self.prompt_center.spec_parser.parse_mode(asset),
        )
        self._mode_cache[cache_key] = loaded
        return loaded

    def load_mode(self, branch: str, mode: str) -> ModeSpec:
        """加载通用分支下的 mode 正式规范。"""
        return self.load_mode_asset(branch, mode).spec


class EducationPromptLoader:
    """负责加载教育域 Skill。"""

    def __init__(self, prompt_center: "PromptCenter") -> None:
        self.prompt_center = prompt_center
        self.registry = PromptSkillRegistry()
        self._branch_cache: PromptSkillAsset[BranchSpec] | None = None
        self._module_cache: dict[str, PromptSkillAsset[ModuleSpec]] = {}
        self._subject_cache: dict[str, PromptSkillAsset[SubjectSpec]] = {}
        self._pedagogy_cache: dict[str, PromptSkillAsset[PedagogySpec]] = {}

    def load_branch_asset(self) -> PromptSkillAsset[BranchSpec]:
        """加载教育分支入口资产。"""
        if self._branch_cache is not None:
            return self._branch_cache
        location = self.registry.education_branch()
        card = self.prompt_center.load_skill_card(location.skill_file)
        asset = self.prompt_center.load_skill_reference_asset(location.skill_file, card.entry_reference)
        self._branch_cache = PromptSkillAsset(
            skill=card,
            spec=self.prompt_center.spec_parser.parse_branch(asset),
        )
        return self._branch_cache

    def load_branch(self) -> BranchSpec:
        """加载教育分支正式规范。"""
        return self.load_branch_asset().spec

    def load_module_asset(self, module: str) -> PromptSkillAsset[ModuleSpec]:
        """加载教育模块资产。"""
        if module in self._module_cache:
            return self._module_cache[module]
        location = self.registry.education_module(module)
        card = self.prompt_center.load_skill_card(location.skill_file)
        asset = self.prompt_center.load_skill_reference_asset(location.skill_file, card.entry_reference)
        loaded = PromptSkillAsset(
            skill=card,
            spec=self.prompt_center.spec_parser.parse_module(asset),
        )
        self._module_cache[module] = loaded
        return loaded

    def load_module(self, module: str) -> ModuleSpec:
        """加载教育模块正式规范。"""
        return self.load_module_asset(module).spec

    def load_subject_asset(self, subject: str) -> PromptSkillAsset[SubjectSpec]:
        """加载教育学科资产。"""
        if subject in self._subject_cache:
            return self._subject_cache[subject]
        location = self.registry.education_subject(subject)
        card = self.prompt_center.load_skill_card(location.skill_file)
        asset = self.prompt_center.load_skill_reference_asset(location.skill_file, card.entry_reference)
        loaded = PromptSkillAsset(
            skill=card,
            spec=self.prompt_center.spec_parser.parse_subject(asset),
        )
        self._subject_cache[subject] = loaded
        return loaded

    def load_subject(self, subject: str) -> SubjectSpec:
        """加载教育学科正式规范。"""
        return self.load_subject_asset(subject).spec

    def load_pedagogy_asset(self, pedagogy: str) -> PromptSkillAsset[PedagogySpec]:
        """加载教育教学法资产。"""
        if pedagogy in self._pedagogy_cache:
            return self._pedagogy_cache[pedagogy]
        location = self.registry.education_pedagogy(pedagogy)
        card = self.prompt_center.load_skill_card(location.skill_file)
        asset = self.prompt_center.load_skill_reference_asset(location.skill_file, card.entry_reference)
        loaded = PromptSkillAsset(
            skill=card,
            spec=self.prompt_center.spec_parser.parse_pedagogy(asset),
        )
        self._pedagogy_cache[pedagogy] = loaded
        return loaded

    def load_pedagogy(self, pedagogy: str) -> PedagogySpec:
        """加载教育教学法正式规范。"""
        return self.load_pedagogy_asset(pedagogy).spec

    def load_assets(
        self,
        *,
        module: str,
        subject: str,
        pedagogy: str,
    ) -> EducationPromptAssets:
        """按一轮教育计划批量加载正式资产。"""
        branch_asset = self.load_branch_asset()
        module_asset = self.load_module_asset(module)
        subject_asset = self.load_subject_asset(subject)
        pedagogy_asset = self.load_pedagogy_asset(pedagogy)
        return EducationPromptAssets(
            branch_skill=branch_asset.skill,
            branch=branch_asset.spec,
            module_skill=module_asset.skill,
            module=module_asset.spec,
            subject_skill=subject_asset.skill,
            subject=subject_asset.spec,
            pedagogy_skill=pedagogy_asset.skill,
            pedagogy=pedagogy_asset.spec,
        )
