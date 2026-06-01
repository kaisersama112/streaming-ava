"""PromptPackage 构造器。

当前模块只负责两类事情：
- 为 router 阶段构造正式系统指令
- 为 responder 阶段按统一 Skill 合同装配 `PromptPackage`

不再直接依赖旧式：
- `core/base`
- `core/contracts`
- 多个分散 renderer
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from .loaders import PromptSkillLoader
from .prompt_loader import PromptCenter
from .specs import PromptPackage, Skill

if TYPE_CHECKING:
    from ava.domain.conversation.strategy import BranchStrategy
    from ava.multi_turn_context_builder.types import ConversationContext

_PROMPT_PACKAGE_CACHE: dict[tuple[str, str, str], PromptPackage] = {}
_ROUTER_SKILL_FILE = "core/router/SKILL.md"
_UNIFIED_RENDERER_FILE = "core/renderer/prompt_renderer.md"


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


def _render_skill_block(skill: Skill) -> str:
    """把 Skill 渲染为统一技能块。"""
    blocks = [
        f"[Skill: {skill.name}]",
        f"Kind: {skill.kind}",
        "",
        "Purpose:",
        skill.purpose.strip(),
        "",
        "Instructions:",
        skill.instructions.strip(),
    ]
    if skill.examples:
        blocks.extend(
            [
                "",
                "Examples:",
                *[f"- {item}" for item in skill.examples],
            ]
        )
    return "\n".join(block for block in blocks if block is not None).strip()


def _render_references(
        *,
        prompt_loader: PromptSkillLoader,
        skill: Skill,
) -> str:
    """把当前 Skill 的引用规范渲染为附加块。"""
    sections: list[str] = []
    for path, text in prompt_loader.load_reference_texts(skill):
        if not text:
            continue
        sections.append(
            "\n".join(
                [
                    f"[Reference: {skill.name}]",
                    f"Path: {path}",
                    text.strip(),
                ]
            ).strip()
        )
    return "\n\n".join(section for section in sections if section).strip()


def _resolve_skill_chain(strategy: "BranchStrategy", prompt_loader: PromptSkillLoader) -> tuple[Skill, list[Skill]]:
    if strategy.branch == "education":
        capability = prompt_loader.load_capability("education")
        tasks = [prompt_loader.load_task(strategy.module or "solve")]
        knowledges = [prompt_loader.load_knowledge(strategy.subject or "general-knowledge")]
        methods = [prompt_loader.load_method((strategy.pedagogy or "step-by-step").replace("_", "-"))]
        audience_name = str(getattr(strategy, "audience", "") or "").strip()
        audiences = [prompt_loader.load_audience(audience_name)] if audience_name else []
        return capability, [*tasks, *knowledges, *methods, *audiences]

    capability = prompt_loader.load_capability("general")
    task_name = (strategy.mode or "fact").replace("_", "-")
    return capability, [prompt_loader.load_task(task_name)]


def _tracked_asset_versions(
        *,
        prompt_center: PromptCenter,
        prompt_loader: PromptSkillLoader,
        skills: list[Skill],
) -> dict[str, dict[str, int]]:
    """收集需要参与 PromptPackage 缓存失效的资产版本。"""
    tracked_files = [_UNIFIED_RENDERER_FILE]
    for skill in skills:
        if skill.source_file:
            tracked_files.append(skill.source_file)
        for relative_path in skill.references:
            skill_resolve_relative = prompt_center.registry.resolve_relative(skill.source_file, relative_path)
            tracked_files.append(skill_resolve_relative)

    asset_versions: dict[str, dict[str, int]] = {}
    for relative_path in dict.fromkeys(tracked_files):
        path = prompt_center._resolve(relative_path)
        stat = path.stat()
        asset_versions[relative_path] = {
            "mtime_ns": stat.st_mtime_ns,
            "size": stat.st_size,
        }
    return asset_versions


def _build_prompt_cache_key(prompt_center: PromptCenter, strategy: "BranchStrategy") -> tuple[str, str, str]:
    """构造 PromptPackage 缓存键。"""
    prompt_loader = PromptSkillLoader(prompt_center)
    capability, layered_skills = _resolve_skill_chain(strategy, prompt_loader)
    asset_versions = _tracked_asset_versions(
        prompt_center=prompt_center,
        prompt_loader=prompt_loader,
        skills=[capability, *layered_skills],
    )
    return (
        str(prompt_center.config.prompt_dir),
        strategy.strategy_id,
        json.dumps(
            {
                "strategy": _cache_safe_value(strategy.to_metadata()),
                "asset_versions": asset_versions,
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
    )


def build_router_system_prompt(prompt_center: PromptCenter) -> str:
    """读取 router 阶段正式 Skill 指令。"""
    loader = PromptSkillLoader(prompt_center)

    router_skill = prompt_center.load_skill(_ROUTER_SKILL_FILE)
    blocks = [_render_skill_block(router_skill)]
    router_references = _render_references(prompt_loader=loader, skill=router_skill)
    if router_references:
        blocks.append(router_references)
    return "\n\n".join(block for block in blocks if block).strip()


def build_router_user_message(context: "ConversationContext") -> dict[str, object]:
    """直接返回当前轮原始标准用户消息。"""
    return dict(context.current.user_message)


def _build_prompt_package(prompt_center: PromptCenter, strategy: "BranchStrategy") -> PromptPackage:
    prompt_loader = PromptSkillLoader(prompt_center)
    capability, layered_skills = _resolve_skill_chain(strategy, prompt_loader)
    all_skills = [capability, *layered_skills]

    renderer_template = prompt_center.render_path(_UNIFIED_RENDERER_FILE, {}).strip()
    skill_blocks = [_render_skill_block(skill) for skill in all_skills]
    reference_blocks = [
        rendered
        for rendered in (_render_references(prompt_loader=prompt_loader, skill=skill) for skill in all_skills)
        if rendered
    ]
    prompt_text = "\n\n".join(
        block
        for block in [
            renderer_template,
            *skill_blocks,
            *reference_blocks,
        ]
        if block
    ).strip()
    return PromptSkillLoader.build_package(
        capability=capability,
        skills=layered_skills,
        prompt=prompt_text,
    )


def _build_prompt_shell(prompt_center: PromptCenter, strategy: "BranchStrategy") -> PromptPackage:
    cache_key = _build_prompt_cache_key(prompt_center, strategy)
    cached = _PROMPT_PACKAGE_CACHE.get(cache_key)
    if cached is not None:
        return cached
    built = _build_prompt_package(prompt_center, strategy)
    _PROMPT_PACKAGE_CACHE[cache_key] = built
    return built


def build_responder_system_prompt(
        prompt_center: PromptCenter,
        context: "ConversationContext",
        strategy: "BranchStrategy",
) -> str:
    """构造 responder 阶段系统指令。"""
    del context
    return _build_prompt_shell(prompt_center, strategy).prompt


def build_responder_prompt_package(
        prompt_center: PromptCenter,
        strategy: "BranchStrategy",
) -> PromptPackage:
    """构造 responder 阶段 PromptPackage。"""
    return _build_prompt_shell(prompt_center, strategy)
