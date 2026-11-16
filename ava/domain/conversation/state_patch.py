"""Agent 状态白名单 patch 机制。

Agent 只能提交 patch 建议，唯一写入点在这里：
- 白名单外的 key 一律拒绝（session_scene / turn_records / memory 等核心事实源不可被 Agent 触碰）
- 每条 patch 的应用 / 拒绝都落 trace，可审计可回放
"""

from __future__ import annotations

from typing import Any

from ava.core.tracing import trace_event

EDUCATION_PATCH_KEYS = frozenset(
    {
        "subject",
        "knowledge_point",
        "stage",
        "level",
        "learning_scenario",
        "learning_objects",
        "object_scope",
        "primary_action",
        "answer_boundary",
        "last_problem",
    }
)

AGENT_PATCH_WHITELIST = frozenset(EDUCATION_PATCH_KEYS | {"recent_topic_hint", "user_facts"})

_MAX_TEXT_VALUE_CHARS = 160
_MAX_LIST_ITEMS = 12
_MAX_FACTS = 24


def _normalize_value(key: str, value: Any) -> Any | None:
    if key == "learning_objects":
        if isinstance(value, str):
            value = [item.strip() for item in value.split(",") if item.strip()]
        if not isinstance(value, (list, tuple)):
            return None
        items = [str(item).strip()[:80] for item in value if str(item or "").strip()]
        return items[:_MAX_LIST_ITEMS] or None
    if key == "user_facts":
        if not isinstance(value, dict):
            return None
        facts = {
            str(k).strip()[:40]: str(v).strip()[:_MAX_TEXT_VALUE_CHARS]
            for k, v in value.items()
            if str(k or "").strip() and str(v or "").strip()
        }
        return dict(list(facts.items())[:_MAX_FACTS]) or None
    if key == "last_problem":
        if isinstance(value, dict):
            return value
        if isinstance(value, str) and value.strip():
            return {"text": value.strip()[:_MAX_TEXT_VALUE_CHARS]}
        return None
    text = str(value or "").strip()
    if not text:
        return None
    return text[:_MAX_TEXT_VALUE_CHARS]


def apply_state_patches(
    state: Any,
    patches: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    *,
    actor: str = "agent",
    trace_id: str = "",
) -> dict[str, list[dict[str, Any]]]:
    """在主线程按序应用白名单 patch，返回 applied / rejected 明细。"""
    applied: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    session_id = str(getattr(state, "session_id", "") or "")
    for raw in list(patches or []):
        patch = dict(raw or {})
        key = str(patch.get("key", "") or "").strip()
        reason = str(patch.get("reason", "") or "").strip()
        source = str(patch.get("actor", "") or actor).strip() or actor
        turn_id = patch.get("turn_id")
        base = {"key": key, "reason": reason}
        detail = {**base, "patch_actor": source}
        if key not in AGENT_PATCH_WHITELIST:
            rejected.append({**detail, "value": patch.get("value"), "reject_reason": "not_in_whitelist"})
            trace_event(
                "state.patch.rejected",
                actor=source,
                session_id=session_id,
                turn_id=turn_id,
                trace_id=trace_id,
                **{**detail, "reject_reason": "not_in_whitelist"},
            )
            continue
        value = _normalize_value(key, patch.get("value"))
        if value is None:
            rejected.append({**detail, "value": patch.get("value"), "reject_reason": "invalid_value"})
            trace_event(
                "state.patch.rejected",
                actor=source,
                session_id=session_id,
                turn_id=turn_id,
                trace_id=trace_id,
                **{**detail, "reject_reason": "invalid_value"},
            )
            continue
        if key == "recent_topic_hint":
            state.memory.append_recent_topic(str(value))
        elif key == "user_facts":
            for fact_key, fact_value in value.items():
                state.memory.set_user_fact(fact_key, fact_value)
        else:
            state.memory.set_education_state_value(key, value)
        applied.append({**detail, "value": value})
        trace_event(
            "state.patch.applied",
            actor=source,
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            **{**detail, "value": value},
        )
    return {"applied": applied, "rejected": rejected}