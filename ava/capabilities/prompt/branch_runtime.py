"""通用分支提示运行时。"""

from __future__ import annotations

from .prompt_loader import PromptCenter
from .prompt_runtime import ModeSpec, PluginSpec, _parse_mode, _parse_plugin


class BranchPromptRuntime:
    """负责加载通用分支的 plugin / mode 资产。"""

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
