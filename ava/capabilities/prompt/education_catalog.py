"""教育提示资产目录入口。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ava.capabilities.prompt.prompt_loader import PromptCenter
from ava.capabilities.prompt.education_runtime import EducationPromptRuntime
from ava.capabilities.prompt.prompt_runtime import (
    ModuleSpec,
    PedagogySpec,
    PluginSpec,
    SubjectSpec,
    _parse_module,
    _parse_pedagogy,
    _parse_plugin,
    _parse_subject,
)


@dataclass(frozen=True)
class EducationPromptAssets:
    """一轮教育回答实际使用到的提示资产集合。"""

    branch: PluginSpec
    module: ModuleSpec
    subject: SubjectSpec
    pedagogy: PedagogySpec


class EducationPromptCatalog:
    """
    教育资产读取入口。

    当前将“教育提示资产如何加载”统一收口到一个类里，
    这样上层业务不需要感知目录布局细节。
    """

    def __init__(self, prompt_center: PromptCenter) -> None:
        self.prompt_center = prompt_center
        self.runtime = EducationPromptRuntime(prompt_center)
        self._root = Path(prompt_center.config.prompt_dir)

    def load_assets(
        self,
        *,
        module: str,
        subject: str,
        pedagogy: str,
    ) -> EducationPromptAssets:
        """
        按教育计划加载分支 / 模块 / 学科 / 教学法资产。

        读取顺序：
        1. 优先读取新目录 `prompt-plugin/education/...`
        2. 若新目录缺少分支或模块、学科等旧资产，再回退到旧运行时入口
        """
        branch_asset = self._load_branch()
        module_asset = self._load_module(module)
        subject_asset = self._load_subject(module, subject)
        pedagogy_asset = self._load_pedagogy(module, pedagogy)
        return EducationPromptAssets(
            branch=branch_asset,
            module=module_asset,
            subject=subject_asset,
            pedagogy=pedagogy_asset,
        )

    def _exists(self, relative_path: str) -> bool:
        """判断相对路径对应的提示资产是否存在。"""
        return self._root.joinpath(relative_path).exists()

    def _load_branch(self) -> PluginSpec:
        """读取教育分支入口。"""
        new_path = "education/branch.md"
        if self._exists(new_path):
            return _parse_plugin(self.prompt_center.load_markdown_asset(new_path))
        return self.runtime.load_branch()

    def _load_module(self, module: str) -> ModuleSpec:
        """读取教育模块资产。"""
        new_path = f"education/modules/{module}.md"
        if self._exists(new_path):
            return _parse_module(self.prompt_center.load_markdown_asset(new_path))
        return self.runtime.load_module(module)

    def _load_subject(self, module: str, subject: str) -> SubjectSpec:
        """
        读取教育学科资产。

        新结构里学科是跨模块共享的，因此优先走统一学科目录；
        若尚未迁移，再回退到旧模块分层结构。
        """
        new_path = f"education/subjects/{subject}.md"
        if self._exists(new_path):
            return _parse_subject(self.prompt_center.load_markdown_asset(new_path))
        return self.runtime.load_subject(module, subject)

    def _load_pedagogy(self, module: str, pedagogy: str) -> PedagogySpec:
        """
        读取教育教学法资产。

        pedagogy 已统一为跨模块共享的稳定教学策略层，
        资产仅从 `prompt-plugin/education/pedagogies/` 读取。
        """
        new_path = f"education/pedagogies/{pedagogy}.md"
        if not self._exists(new_path):
            return self.runtime.load_pedagogy(module, pedagogy)
        return _parse_pedagogy(self.prompt_center.load_markdown_asset(new_path))
