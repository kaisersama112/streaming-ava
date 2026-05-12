"""Builders that turn domain/application context into concrete prompts."""

from __future__ import annotations

import json
from typing import Any

from ava.domain.conversation import ContextSnapshot
from ava.domain.conversation.strategy import BranchStrategy

from .prompt_loader import PromptCenter

_PROMPT_SHELL_CACHE: dict[tuple[str, str, str], str] = {}


def build_router_system_prompt(prompt_center: PromptCenter) -> str:
    return prompt_center.get("router")


def _router_context_text(
    snapshot: ContextSnapshot,
) -> str:
    return snapshot.user_text or "无"


def build_router_user_message(
    snapshot: ContextSnapshot,
    *,
    text_only: bool = False,
) -> dict[str, object]:
    user_content: list[dict[str, object]] = [
        {"type": "text", "text": _router_context_text(snapshot)}
    ]

    if not text_only:
        for artifact in snapshot.artifacts:
            block = artifact.to_message_block()
            if block:
                user_content.append(block)

        if not snapshot.artifacts and snapshot.reference_artifacts:
            for artifact in snapshot.reference_artifacts:
                block = artifact.to_message_block()
                if block:
                    user_content.append(block)

    return {"role": "user", "content": user_content}


def _cache_safe_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _cache_safe_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_cache_safe_value(item) for item in value]
    return str(value)


def _build_prompt_shell_cache_key(prompt_center: PromptCenter, strategy: BranchStrategy) -> tuple[str, str, str]:
    spec = strategy.resolved_prompt_spec
    if spec is None:
        raise ValueError("resolved_prompt_spec is required")
    asset_versions: dict[str, dict[str, int]] = {}
    for relative_path in (*spec.base_files, spec.contract_file, spec.renderer_file):
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
                "variables": _cache_safe_value(spec.variables),
                "asset_versions": asset_versions,
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
    )


def _build_prompt_shell_from_spec(
    prompt_center: PromptCenter,
    strategy: BranchStrategy,
) -> str:
    spec = strategy.resolved_prompt_spec
    if spec is None:
        raise ValueError("resolved_prompt_spec is required")

    shell_variables = dict(spec.variables)
    blocks: list[str] = []
    for path in spec.base_files:
        rendered = prompt_center.render_path(path, shell_variables).strip()
        if rendered:
            blocks.append(rendered)

    if spec.contract_file:
        rendered_contract = prompt_center.render_path(spec.contract_file, shell_variables).strip()
        if rendered_contract:
            blocks.append(rendered_contract)

    rendered_template = prompt_center.render_path(spec.renderer_file, shell_variables).strip()
    if rendered_template:
        blocks.append(rendered_template)

    return "\n\n".join(block for block in blocks if block).strip()


def _build_prompt_shell(
    prompt_center: PromptCenter,
    strategy: BranchStrategy,
) -> str:
    cache_key = _build_prompt_shell_cache_key(prompt_center, strategy)
    shell = _PROMPT_SHELL_CACHE.get(cache_key)
    if shell is not None:
        return shell
    shell = _build_prompt_shell_from_spec(prompt_center, strategy)
    _PROMPT_SHELL_CACHE[cache_key] = shell
    return shell


def _build_system_prompt_from_spec(
    prompt_center: PromptCenter,
    snapshot: ContextSnapshot,
    strategy: BranchStrategy,
) -> str:
    spec = strategy.resolved_prompt_spec
    if spec is None:
        raise ValueError("resolved_prompt_spec is required")

    return _build_prompt_shell(prompt_center, strategy).strip()


def build_responder_system_prompt(
    prompt_center: PromptCenter,
    snapshot: ContextSnapshot,
    strategy: BranchStrategy,
) -> str:
    if strategy.resolved_prompt_spec is not None:
        return _build_system_prompt_from_spec(prompt_center, snapshot, strategy)

    raise ValueError(f"Branch strategy {strategy.strategy_id} is missing resolved_prompt_spec")



