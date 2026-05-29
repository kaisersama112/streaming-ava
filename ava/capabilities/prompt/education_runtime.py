"""教育提示运行时。"""

from __future__ import annotations

from .prompt_loader import PromptCenter
from .prompt_runtime import (
    ModuleSpec,
    PedagogySpec,
    PluginSpec,
    SubjectSpec,
    _parse_module,
    _parse_pedagogy,
    _parse_plugin,
    _parse_subject,
)


class EducationPromptRuntime:
    """负责加载教育域的 branch / module / subject / pedagogy 资产。"""

    def __init__(self, prompt_center: PromptCenter):
        self.prompt_center = prompt_center
        self._plugin_cache: dict[str, PluginSpec] = {}
        self._module_cache: dict[str, ModuleSpec] = {}
        self._subject_cache: dict[tuple[str, str], SubjectSpec] = {}
        self._pedagogy_cache: dict[tuple[str, str], PedagogySpec] = {}

    def load_branch(self) -> PluginSpec:
        if "education" in self._plugin_cache:
            return self._plugin_cache["education"]
        plugin = _parse_plugin(self.prompt_center.load_markdown_asset("education/branch.md"))
        self._plugin_cache["education"] = plugin
        return plugin

    def load_module(self, module: str) -> ModuleSpec:
        if module in self._module_cache:
            return self._module_cache[module]
        module_spec = _parse_module(self.prompt_center.load_markdown_asset(f"education/modules/{module}.md"))
        self._module_cache[module] = module_spec
        return module_spec

    def load_subject(self, module: str, subject: str) -> SubjectSpec:
        cache_key = (module, subject)
        if cache_key in self._subject_cache:
            return self._subject_cache[cache_key]
        asset = self.prompt_center.load_markdown_asset(f"education/subjects/{subject}.md")
        subject_spec = _parse_subject(asset)
        self._subject_cache[cache_key] = subject_spec
        return subject_spec

    def load_pedagogy(self, module: str, pedagogy: str) -> PedagogySpec:
        """加载教育域教学法资产。"""
        cache_key = (module, pedagogy)
        if cache_key in self._pedagogy_cache:
            return self._pedagogy_cache[cache_key]
        asset = self.prompt_center.load_markdown_asset(f"education/pedagogies/{pedagogy}.md")
        pedagogy_spec = _parse_pedagogy(asset)
        self._pedagogy_cache[cache_key] = pedagogy_spec
        return pedagogy_spec
