"""Builders that turn domain/application context into concrete prompts."""

from __future__ import annotations

import json
import re
from typing import Any

import yaml
from ava.domain.context import ContextSnapshot
from ava.domain.strategy import BranchStrategy

from .loader import PromptCenter

_PROMPT_SHELL_CACHE: dict[tuple[str, str, str], str] = {}
_RUNTIME_SECTION_PATTERNS = (
    r"\n*当前用户问题：\n(?:[^\n]*\n?)*?(?=\n(?:最近上下文摘要：|最近轮摘要：|多模态摘要：|facts:|education_state:|请直接输出自然中文回答：)|\Z)",
    r"\n*最近上下文摘要：\n(?:[^\n]*\n?)*?(?=\n(?:最近轮摘要：|多模态摘要：|facts:|education_state:|请直接输出自然中文回答：)|\Z)",
    r"\n*最近轮摘要：\n(?:[^\n]*\n?)*?(?=\n(?:多模态摘要：|facts:|education_state:|请直接输出自然中文回答：)|\Z)",
    r"\n*多模态摘要：\n(?:[^\n]*\n?)*?(?=\n(?:facts:|education_state:|请直接输出自然中文回答：)|\Z)",
    r"\n*facts:\n(?:[^\n]*\n?)*?(?=\n(?:education_state:|请直接输出自然中文回答：)|\Z)",
    r"\n*education_state:\n(?:[^\n]*\n?)*?(?=\n请直接输出自然中文回答：|\Z)",
)


def build_router_system_prompt(prompt_center: PromptCenter) -> str:
    return prompt_center.get("router")


def _recent_completed_turn_router_context(snapshot: ContextSnapshot, limit: int = 3) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for record in reversed(list(getattr(snapshot, "turn_records", []) or [])):
        if str(record.get("turn_status", "completed") or "completed").strip() == "pending":
            continue
        decision = dict(record.get("decision") or {})
        strategy = dict(record.get("strategy") or {})
        analysis = dict(strategy.get("analysis") or {})
        frame = dict(analysis.get("education_turn_frame") or analysis.get("task_frame") or {})
        items.append(
            {
                "user_text": str(record.get("user_text", "") or "").strip(),
                "assistant_text": str(record.get("assistant_text", "") or "").strip(),
                "session_scene": str(decision.get("session_scene") or "").strip(),
                "turn_scene": str(decision.get("turn_scene") or "").strip(),
                "intent": str(decision.get("intent") or "").strip(),
                "strategy_id": str(strategy.get("strategy_id") or "").strip(),
                "policy_id": str(strategy.get("policy_id") or "").strip(),
                "primary_scenario": str(frame.get("primary_scenario") or "").strip(),
                "primary_action": str(frame.get("primary_action") or "").strip(),
                "object_scope": str(frame.get("object_scope") or "").strip(),
                "object_continuity": str(frame.get("object_continuity") or "").strip(),
            }
        )
        if len(items) >= limit:
            break
    items.reverse()
    return items


def _compact_router_education_state(snapshot: ContextSnapshot) -> dict[str, Any]:
    state = dict(getattr(snapshot, "education_state", {}) or {})
    keys = (
        "subject",
        "learning_scenario",
        "learning_objects",
        "object_scope",
        "object_continuity",
        "primary_action",
        "secondary_actions",
        "answer_boundary",
        "previous_branch",
        "previous_strategy_id",
        "previous_policy_id",
    )
    compact: dict[str, Any] = {}
    for key in keys:
        value = state.get(key)
        if value in (None, "", [], {}, ()):
            continue
        compact[key] = value
    return compact


def _router_context_text(
    snapshot: ContextSnapshot,
    *,
    artifact_brief: dict[str, object] | None = None,
    text_brief: dict[str, object] | None = None,
) -> str:
    recent_turns = _recent_completed_turn_router_context(snapshot, limit=3)
    lines = [
        "请基于当前输入和最近几轮对话，直接输出本轮 RouteDecision 与 TurnPlan 选择结果。",
        "JSON Schema:",
        "{",
        '  "session_scene": "education|general",',
        '  "turn_scene": "education|general_qa|casual_chat|clarify",',
        '  "intent": "string",',
        '  "confidence": 0.0,',
        '  "should_preserve_teaching_state": true,',
        '  "need_clarification": false,',
        '  "plan": {',
        '    "branch": "education|general_qa|casual_chat|clarify",',
        '    "mode": "fact|reasoned|howto|compare|troubleshoot|visual|confirm|reaction|praise|backchannel|companion|humor|smalltalk|missing_material|focus|missing_reference|answer_mode|scene|subject",',
        '    "module": "solve|check|explain|drill|answer|qa",',
        '    "subject": "math|english|chinese|cs|physics|history|general",',
        '    "style": "direct|explain_careful|hint_only|step_by_step",',
        '    "policy_id": "string",',
        '    "primary_scenario": "practice|lesson|concept|qa|general",',
        '    "primary_action": "string",',
        '    "learning_objects": ["string"],',
        '    "object_scope": "string",',
        '    "object_continuity": "same|new|uncertain",',
        '    "answer_boundary": "hint_first|full_solution|direct_explain|contextual_only|targeted_answer",',
        '    "prompt_overrides": ["string"],',
        '    "plan_reason": "string"',
        "  }",
        "}",
        "",
        "当前轮意图必须结合当前用户文本、最近原始问答、会话状态和附件本身综合判断。",
        "请先判断当前这一轮是在延续前几轮中的哪个对象，还是明确切换了新主题。",
        "不要因为用户当前文本很短，就忽略最近对话历史。",
        "你需要在这一次输出里同时给出 route 和 plan，不要省略 plan，也不要把 plan 留给后续规则去补。",
        "如果是 education，plan 必须直接给出 module / subject / style / policy_id / primary_action 等关键选择。",
        "如果是 general_qa、casual_chat 或 clarify，plan 必须直接给出 mode。",
        "",
        f"当前用户文本：{snapshot.user_text or '无'}",
        f"当前会话主场景：{snapshot.session_scene or 'unknown'}",
        f"最近相关上下文：{snapshot.recent_history_summary or '无'}",
        f"最近轮摘要：{snapshot.recent_turns_summary or '无'}",
        f"多模态摘要：{snapshot.multimodal_summary or '无'}",
    ]
    if snapshot.history_messages:
        lines.append("最近几轮原始问答已随 messages 提供，请结合这些原始问答判断当前这一轮意图。")
    for index, turn in enumerate(recent_turns, start=1):
        lines.append(
            f"最近已完成第{index}条参考轮次："
            f"session_scene={turn.get('session_scene') or 'unknown'}, "
            f"turn_scene={turn.get('turn_scene') or 'unknown'}, "
            f"intent={turn.get('intent') or 'unknown'}"
        )
        if turn.get("strategy_id"):
            lines.append(f"最近第{index}条参考轮次策略：{turn['strategy_id']}")
        if turn.get("primary_scenario") or turn.get("primary_action"):
            lines.append(
                f"最近第{index}条参考轮次教学框架："
                f"scenario={turn.get('primary_scenario') or 'unknown'}, "
                f"action={turn.get('primary_action') or 'unknown'}, "
                f"object_scope={turn.get('object_scope') or 'unknown'}, "
                f"object_continuity={turn.get('object_continuity') or 'unknown'}"
            )
    if artifact_brief:
        lines.append(f"当前附件理解：{json.dumps(artifact_brief, ensure_ascii=False)}")
    if text_brief:
        lines.append(f"当前文本理解：{json.dumps(text_brief, ensure_ascii=False)}")
    if snapshot.facts:
        lines.append(f"已知事实：{json.dumps(snapshot.facts, ensure_ascii=False)}")
    compact_education_state = _compact_router_education_state(snapshot)
    if compact_education_state:
        lines.append(f"教学状态：{json.dumps(compact_education_state, ensure_ascii=False)}")
    if snapshot.reference_artifacts and not snapshot.artifacts:
        lines.append("如果当前问题明显是在继续追问之前的参考素材，请结合这些参考素材一起判断。")
    return "\n".join(lines).strip()


def build_router_user_message(
    snapshot: ContextSnapshot,
    *,
    text_only: bool = False,
    artifact_brief: dict[str, object] | None = None,
    text_brief: dict[str, object] | None = None,
) -> dict[str, object]:
    user_content: list[dict[str, object]] = [{"type": "text", "text": _router_context_text(snapshot, artifact_brief=artifact_brief, text_brief=text_brief)}]

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


def _format_list(items: tuple[str, ...] | list[str]) -> str:
    values = [str(item).strip() for item in items if str(item).strip()]
    if not values:
        return "- 无"
    return "\n".join(f"- {item}" for item in values)


def _dump_yaml(data: dict[str, Any]) -> str:
    payload = data or {}
    return yaml.safe_dump(payload, allow_unicode=True, sort_keys=False).strip() or "{}"


def _compact_text(text: str | None, limit: int) -> str:
    value = str(text or "").strip()
    if len(value) <= limit:
        return value
    return f"{value[:limit].rstrip()}…"


def _has_direct_media_blocks(snapshot: ContextSnapshot) -> bool:
    for artifact in getattr(snapshot, "artifacts", ()) or ():
        if artifact.to_message_block():
            return True
    return False


def _has_history_messages(snapshot: ContextSnapshot) -> bool:
    return bool(getattr(snapshot, "history_messages", []) or [])


def _compact_education_state(snapshot: ContextSnapshot) -> dict[str, Any]:
    state = dict(getattr(snapshot, "education_state", {}) or {})
    keys = (
        "subject",
        "knowledge_point",
        "stage",
        "level",
        "learning_scenario",
        "learning_objects",
        "object_scope",
        "object_continuity",
        "primary_action",
        "secondary_actions",
        "answer_boundary",
    )
    compact: dict[str, Any] = {}
    for key in keys:
        value = state.get(key)
        if value in (None, "", [], {}, ()):
            continue
        compact[key] = value
    return compact


def _normalize_variable_map(variables: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in (variables or {}).items():
        if isinstance(value, (list, tuple)):
            normalized[key] = _format_list(value)
        elif isinstance(value, dict):
            normalized[key] = _dump_yaml(value)
        else:
            normalized[key] = value
    return normalized


def _cache_safe_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _cache_safe_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_cache_safe_value(item) for item in value]
    return str(value)


def _prompt_context_policy(strategy: BranchStrategy) -> dict[str, bool]:
    analysis = dict(getattr(strategy, "analysis", {}) or {})
    continuity = dict(analysis.get("continuity", {}) or {})
    configured = dict(analysis.get("prompt_context_policy", {}) or {})
    is_followup = bool(continuity.get("current_turn_is_followup", analysis.get("current_turn_is_followup")))
    same_object = str(continuity.get("object_continuity") or "").strip() == "same"
    style_only = bool(analysis.get("user_requests_style_change_only"))
    education_turn_frame = dict(analysis.get("education_turn_frame", {}) or {})
    scenario_policy = dict(education_turn_frame.get("scenario_policy", {}) or {})
    answer_boundary = str(scenario_policy.get("answer_boundary") or analysis.get("answer_boundary") or "").strip()
    return {
        "include_recent_history_summary": bool(
            configured.get(
                "include_recent_history_summary",
                analysis.get("include_recent_history_summary", is_followup or same_object or style_only or answer_boundary == "contextual_only"),
            )
        ),
        "include_recent_turns_summary": bool(configured.get("include_recent_turns_summary", analysis.get("include_recent_turns_summary", False))),
        "include_multimodal_summary": bool(configured.get("include_multimodal_summary", analysis.get("include_multimodal_summary", False))),
        "include_facts": bool(configured.get("include_facts_in_prompt", analysis.get("include_facts_in_prompt", False))),
    }


def _shared_context_block(snapshot: ContextSnapshot, strategy: BranchStrategy) -> str:
    policy = _prompt_context_policy(strategy)
    analysis = dict(getattr(strategy, "analysis", {}) or {})
    education_turn_frame = dict(analysis.get("education_turn_frame", {}) or {})
    scenario_policy = dict(education_turn_frame.get("scenario_policy", {}) or {})
    history_messages_included = _has_history_messages(snapshot)
    blocks = ["\n\n当前任务上下文："]
    blocks.append(f"- 当前问题: {snapshot.user_text or '无'}")
    if education_turn_frame:
        blocks.append(f"- 学习主场景: {education_turn_frame.get('primary_scenario', 'unknown')}")
        learning_objects = [str(item).strip() for item in (education_turn_frame.get("learning_objects") or []) if str(item).strip()]
        if learning_objects:
            blocks.append(f"- 学习对象: {', '.join(learning_objects)}")
        if education_turn_frame.get("object_scope"):
            blocks.append(f"- 对象范围: {education_turn_frame.get('object_scope')}")
        if education_turn_frame.get("object_continuity"):
            blocks.append(f"- 对象连续性: {education_turn_frame.get('object_continuity')}")
        blocks.append(f"- 当前教学动作: {education_turn_frame.get('primary_action', '') or 'unknown'}")
        secondary_actions = [str(item).strip() for item in (education_turn_frame.get("secondary_actions") or []) if str(item).strip()]
        if secondary_actions:
            blocks.append(f"- 辅助动作: {', '.join(secondary_actions)}")
        evidence_sources = [str(item).strip() for item in (education_turn_frame.get("evidence_sources") or []) if str(item).strip()]
        if evidence_sources:
            blocks.append(f"- 证据源: {', '.join(evidence_sources)}")
        if scenario_policy.get("answer_boundary"):
            blocks.append(f"- 回答边界: {scenario_policy.get('answer_boundary')}")
    if history_messages_included:
        blocks.append("- 最近几轮原始问答已随 messages 提供。")
        short_summary = snapshot.recent_history_summary or snapshot.recent_turns_summary
        if short_summary:
            blocks.append(f"- 历史摘要: {_compact_text(short_summary, 120)}")
    else:
        if policy["include_recent_history_summary"] and snapshot.recent_history_summary:
            blocks.append(f"- 最近相关上下文: {_compact_text(snapshot.recent_history_summary, 360)}")
        if policy["include_recent_turns_summary"] and snapshot.recent_turns_summary:
            blocks.append(f"- 最近轮摘要: {_compact_text(snapshot.recent_turns_summary, 280)}")
    if policy["include_multimodal_summary"] and snapshot.multimodal_summary and not _has_direct_media_blocks(snapshot):
        blocks.append(f"- 多模态摘要: {_compact_text(snapshot.multimodal_summary, 240)}")
    if snapshot.router_artifact_brief:
        blocks.append(f"- 附件结构化理解: {json.dumps(snapshot.router_artifact_brief, ensure_ascii=False)}")
    if policy["include_facts"] and snapshot.facts:
        blocks.append(f"- facts: {json.dumps(snapshot.facts, ensure_ascii=False)}")
    if snapshot.education_state:
        blocks.append(f"- education_state: {json.dumps(_compact_education_state(snapshot), ensure_ascii=False)}")
    scenario_prompt_overrides = [
        str(item).strip()
        for item in (analysis.get("scenario_prompt_overrides") or [])
        if str(item).strip()
    ]
    if scenario_prompt_overrides:
        blocks.append("- 场景约束:")
        blocks.extend(f"  - {item}" for item in scenario_prompt_overrides)
    return "\n".join(blocks).strip()


def _runtime_placeholder_variables() -> dict[str, Any]:
    return {
        "user_text": "",
        "multimodal_summary": "",
        "recent_turns_summary": "",
        "recent_history_summary": "",
        "facts_json": "{}",
        "education_state_json": "{}",
    }


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


def _strip_runtime_sections(text: str) -> str:
    rendered = text
    for pattern in _RUNTIME_SECTION_PATTERNS:
        rendered = re.sub(pattern, "\n", rendered, flags=re.MULTILINE)
    rendered = re.sub(r"\n{3,}", "\n\n", rendered)
    return rendered.strip()


def _build_prompt_shell_from_spec(
    prompt_center: PromptCenter,
    strategy: BranchStrategy,
) -> str:
    spec = strategy.resolved_prompt_spec
    if spec is None:
        raise ValueError("resolved_prompt_spec is required")

    shell_variables = {
        **spec.variables,
        **_runtime_placeholder_variables(),
    }
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
        blocks.append(_strip_runtime_sections(rendered_template))

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

    _normalize_variable_map(spec.variables)

    blocks = [
        _build_prompt_shell(prompt_center, strategy),
        _shared_context_block(snapshot, strategy),
    ]
    return "\n\n".join(block for block in blocks if block).strip()


def build_responder_system_prompt(
    prompt_center: PromptCenter,
    snapshot: ContextSnapshot,
    strategy: BranchStrategy,
) -> str:
    if strategy.resolved_prompt_spec is not None:
        return _build_system_prompt_from_spec(prompt_center, snapshot, strategy)

    raise ValueError(f"Branch strategy {strategy.strategy_id} is missing resolved_prompt_spec")
