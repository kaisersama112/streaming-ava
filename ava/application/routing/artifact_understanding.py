"""Multimodal attachment understanding used before text-only router intent parsing."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from ava.application.trace import append_trace_log
from ava.domain.context import ContextSnapshot
from ava.infrastructure.llm import bigmodel_client
from config import settings

_ARTIFACT_BRIEF_CACHE: dict[str, dict[str, Any]] = {}


def _extract_json_payload(raw: str) -> dict[str, Any]:
    text = str(raw or "").strip()
    if not text:
        raise ValueError("empty artifact understanding response")
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    if text.startswith("{") and text.endswith("}"):
        return dict(json.loads(text))
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return dict(json.loads(text[start : end + 1]))
    raise ValueError("no json object found")


def _cache_key(snapshot: ContextSnapshot) -> str:
    parts: list[str] = []
    for artifact in snapshot.artifacts:
        ref = artifact.data_url or artifact.uri or artifact.name
        digest = hashlib.sha256(str(ref).encode("utf-8")).hexdigest()[:16]
        parts.append(f"{artifact.kind}:{artifact.name}:{digest}:{artifact.summary[:32]}")
    return "|".join(parts)


def _system_prompt() -> str:
    return (
        "你是附件内容理解器。"
        "先理解当前附件，再输出一个 JSON 对象，不要输出任何额外文本。"
        "字段必须包含：summary, subject_hint, task_hint, contains_student_work, contains_lesson_context, contains_sub_problem, contains_problem_statement, education_relevance。"
        "summary 用一句中文概括当前附件的主要内容。"
        "subject_hint 仅可取 math|english|chinese|physics|history|general|unknown。"
        "task_hint 仅可取 solve_problem|check_solution|lesson_context|concept_explain|exercise_generation|unknown。"
        "education_relevance 仅可取 strong|medium|weak。"
    )


def _user_message(snapshot: ContextSnapshot) -> dict[str, Any]:
    content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": (
                f"当前用户文本：{snapshot.user_text or '无'}\n"
                "只分析当前附件，不参考历史题目。"
            ),
        }
    ]
    for artifact in snapshot.artifacts:
        block = artifact.to_message_block()
        if block:
            content.append(block)
        else:
            content.append(
                {
                    "type": "text",
                    "text": f"附件信息：kind={artifact.kind}, name={artifact.name}, summary={artifact.summary or '无'}",
                }
            )
    return {"role": "user", "content": content}


def _fallback_from_metadata(snapshot: ContextSnapshot) -> dict[str, Any]:
    artifact = snapshot.artifacts[0]
    metadata = dict(artifact.metadata or {})
    return {
        "summary": str(artifact.summary or "").strip(),
        "subject_hint": str(metadata.get("subject_hint") or "").strip() or "unknown",
        "task_hint": str(metadata.get("task_hint") or "").strip() or "unknown",
        "contains_student_work": bool(metadata.get("contains_student_work")),
        "contains_lesson_context": bool(metadata.get("contains_lesson_context")),
        "contains_sub_problem": bool(metadata.get("contains_sub_problem")),
        "contains_problem_statement": bool(metadata.get("contains_problem_statement")),
        "education_relevance": "medium" if metadata.get("artifact_role") in {"problem_material", "answer_sheet", "lesson_clip"} else "weak",
    }


def resolve_router_artifact_brief(
    snapshot: ContextSnapshot,
    *,
    timeout: int,
    turn_id: int | None = None,
) -> dict[str, Any]:
    if not snapshot.artifacts:
        return {}
    if not any(artifact.kind in {"image", "audio", "video"} for artifact in snapshot.artifacts):
        return _fallback_from_metadata(snapshot)

    multimodal_model = settings.openai_config.multimodal_model or settings.openai_config.model
    if not (settings.openai_config.api_key and settings.openai_config.api_base and multimodal_model):
        return _fallback_from_metadata(snapshot)

    cache_key = _cache_key(snapshot)
    cached = _ARTIFACT_BRIEF_CACHE.get(cache_key)
    if cached is not None:
        return cached

    try:
        raw = bigmodel_client.multimodal_chat(
            api_base=settings.openai_config.api_base,
            api_key=settings.openai_config.api_key,
            model=multimodal_model,
            timeout=min(max(3, timeout), 10),
            messages=[
                {"role": "system", "content": _system_prompt()},
                _user_message(snapshot),
            ],
        )
        payload = _extract_json_payload(raw)
        brief = {
            "summary": str(payload.get("summary") or "").strip(),
            "subject_hint": str(payload.get("subject_hint") or "unknown").strip() or "unknown",
            "task_hint": str(payload.get("task_hint") or "unknown").strip() or "unknown",
            "contains_student_work": bool(payload.get("contains_student_work")),
            "contains_lesson_context": bool(payload.get("contains_lesson_context")),
            "contains_sub_problem": bool(payload.get("contains_sub_problem")),
            "contains_problem_statement": bool(payload.get("contains_problem_statement")),
            "education_relevance": str(payload.get("education_relevance") or "weak").strip() or "weak",
        }
    except Exception as exc:
        brief = _fallback_from_metadata(snapshot)
        append_trace_log(
            "router.artifact_understanding.fallback",
            {
                "error": str(exc),
                "brief": brief,
            },
            turn_id=turn_id,
            scope="router",
        )
        return brief

    if len(_ARTIFACT_BRIEF_CACHE) >= 64:
        _ARTIFACT_BRIEF_CACHE.pop(next(iter(_ARTIFACT_BRIEF_CACHE)))
    _ARTIFACT_BRIEF_CACHE[cache_key] = brief
    append_trace_log(
        "router.artifact_understanding",
        {
            "brief": brief,
        },
        turn_id=turn_id,
        scope="router",
    )
    return brief

