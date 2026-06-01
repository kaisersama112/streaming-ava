"""Prompt 构造器。

当前模块只负责两件事：
1. 构造 router 阶段系统指令与当前用户消息
2. 基于 `PromptSkillCard + 正式 Spec` 组合 responder 阶段系统指令

注意：
- 不再消费旧的“路径 + 变量字典”式 prompt spec
- 不再从业务层拼接散乱 prompt 片段
- 当前输入与历史消息通过 `input` 数组传给模型，不在这里做单独文本化复制
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ava.domain.conversation.strategy import BranchStrategy
    from ava.multi_turn_context_builder.types import ConversationContext

from .prompt_loader import PromptCenter

_PROMPT_SHELL_CACHE: dict[tuple[str, str, str], str] = {}
_CORE_BASE_FILES = (
    "core/base/persona.md",
    "core/base/multimodal_rules.md",
)


def build_router_system_prompt(prompt_center: PromptCenter) -> str:
    """读取 router 阶段系统指令。"""
    return prompt_center.get("router")


def build_router_user_message(
    context: "ConversationContext",
) -> dict[str, object]:
    """直接返回当前轮原始标准用户消息。"""
    return dict(context.current.user_message)


def _cache_safe_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _cache_safe_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_cache_safe_value(item) for item in value]
    if hasattr(value, "to_metadata") and callable(value.to_metadata):
        return value.to_metadata()
    if hasattr(value, "__dict__"):
        return {str(key): _cache_safe_value(item) for key, item in value.__dict__.items()}
    return str(value)


def _build_contract_path(delivery_mode: str) -> str:
    """根据交付模式得到合同模板路径。"""
    return f"core/contracts/{delivery_mode}.md"


def _build_renderer_path(composition: str) -> str:
    """根据组合类型得到渲染模板路径。"""
    if composition == "education":
        return "core/renderer/education_renderer.md"
    return "core/renderer/mode_renderer.md"


def _renderer_variables(strategy: "BranchStrategy") -> dict[str, Any]:
    """构造渲染模板变量。

    这里只暴露新 Prompt Skill 体系里的正式对象：
    - `PromptSkillCard`
    - `BranchSpec / ModeSpec / ModuleSpec / SubjectSpec / PedagogySpec`
    """
    spec = strategy.resolved_prompt_spec
    if spec is None:
        raise ValueError("resolved_prompt_spec is required")
    variables: dict[str, Any] = {
        "branch": strategy.branch,
        "delivery_mode": strategy.delivery_mode,
        "ui_mode": strategy.ui_mode,
        "selection": strategy.selection,
        "selection_trace": strategy.selection_trace,
        "branch_skill": spec.branch_skill,
        "branch_spec": spec.branch_spec,
        "branch": spec.branch_spec,
    }
    if spec.mode_skill is not None:
        variables["mode_skill"] = spec.mode_skill
    if spec.mode_spec is not None:
        variables["mode"] = spec.mode_spec
    if spec.module_skill is not None:
        variables["module_skill"] = spec.module_skill
    if spec.module_spec is not None:
        variables["module"] = spec.module_spec
    if spec.subject_skill is not None:
        variables["subject_skill"] = spec.subject_skill
    if spec.subject_spec is not None:
        variables["subject"] = spec.subject_spec
    if spec.pedagogy_skill is not None:
        variables["pedagogy_skill"] = spec.pedagogy_skill
    if spec.pedagogy_spec is not None:
        variables["pedagogy"] = spec.pedagogy_spec
    return variables


def _build_prompt_shell_cache_key(prompt_center: PromptCenter, strategy: "BranchStrategy") -> tuple[str, str, str]:
    """构造 responder 系统指令缓存键。"""
    spec = strategy.resolved_prompt_spec
    if spec is None:
        raise ValueError("resolved_prompt_spec is required")

    contract_path = _build_contract_path(spec.delivery_mode)
    renderer_path = _build_renderer_path(spec.composition)
    asset_versions: dict[str, dict[str, int]] = {}
    for relative_path in (*_CORE_BASE_FILES, contract_path, renderer_path):
        if not relative_path:
            continue
        path = prompt_center._resolve(relative_path)
        stat = path.stat()
        asset_versions[relative_path] = {
            "mtime_ns": stat.st_mtime_ns,
            "size": stat.st_size,
        }
    return (
        str(prompt_center.config.prompt_dir),
        strategy.strategy_id,
        json.dumps(
            {
                "spec": spec.to_metadata(),
                "strategy": _cache_safe_value(strategy.to_metadata()),
                "renderer_variables": _cache_safe_value(_renderer_variables(strategy)),
                "asset_versions": asset_versions,
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
    )


def _build_prompt_shell_from_spec(
    prompt_center: PromptCenter,
    strategy: "BranchStrategy",
) -> str:
    """根据 Skill 卡片与正式 Spec 组合稳定系统指令外壳。"""
    spec = strategy.resolved_prompt_spec
    if spec is None:
        raise ValueError("resolved_prompt_spec is required")

    shell_variables = _renderer_variables(strategy)
    blocks: list[str] = []
    for path in _CORE_BASE_FILES:
        rendered = prompt_center.render_path(path, shell_variables).strip()
        if rendered:
            blocks.append(rendered)

    contract_path = _build_contract_path(spec.delivery_mode)
    rendered_contract = prompt_center.render_path(contract_path, shell_variables).strip()
    if rendered_contract:
        blocks.append(rendered_contract)

    renderer_path = _build_renderer_path(spec.composition)
    rendered_renderer = prompt_center.render_path(renderer_path, shell_variables).strip()
    if rendered_renderer:
        blocks.append(rendered_renderer)

    return "\n\n".join(block for block in blocks if block).strip()


def _build_prompt_shell(
    prompt_center: PromptCenter,
    strategy: "BranchStrategy",
) -> str:
    """带缓存地构造 responder 系统指令。"""
    cache_key = _build_prompt_shell_cache_key(prompt_center, strategy)
    shell = _PROMPT_SHELL_CACHE.get(cache_key)
    if shell is not None:
        return shell
    shell = _build_prompt_shell_from_spec(prompt_center, strategy)
    _PROMPT_SHELL_CACHE[cache_key] = shell
    return shell


def _build_system_prompt_from_spec(
    prompt_center: PromptCenter,
    context: "ConversationContext",
    strategy: "BranchStrategy",
) -> str:
    """根据新 Prompt Skill 体系构造 responder 系统指令。"""
    del context
    spec = strategy.resolved_prompt_spec
    if spec is None:
        raise ValueError("resolved_prompt_spec is required")
    return _build_prompt_shell(prompt_center, strategy).strip()


def build_responder_system_prompt(
    prompt_center: PromptCenter,
    context: "ConversationContext",
    strategy: "BranchStrategy",
) -> str:
    """构造 responder 阶段系统指令。"""
    if strategy.resolved_prompt_spec is not None:
        return _build_system_prompt_from_spec(prompt_center, context, strategy)

    raise ValueError(f"Branch strategy {strategy.strategy_id} is missing resolved_prompt_spec")



