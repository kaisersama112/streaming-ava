"""Text-only current-turn understanding used before router intent parsing."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from ava.application.trace import append_trace_log
from ava.domain.context import ContextSnapshot
from ava.infrastructure.llm import client as llm_client
from config import settings

_TEXT_BRIEF_CACHE: dict[str, dict[str, Any]] = {}

_MATH_HINTS = (
    "数学",
    "函数",
    "方程",
    "几何",
    "导数",
    "极限",
    "积分",
    "定积分",
    "二重积分",
    "三重积分",
    "曲线积分",
    "格林公式",
    "正向边界",
    "三角区域",
    "坐标",
)
_ENGLISH_HINTS = ("英语", "英文", "单词", "句子", "语法", "翻译", "阅读", "完形", "比较级", "倒装")
_CHINESE_HINTS = ("语文", "文言文", "古诗", "作文", "病句", "修辞")
_PHYSICS_HINTS = ("物理", "实验", "电路", "受力", "电流", "电压", "滑轮", "杠杆")
_HISTORY_HINTS = ("历史", "古代史", "中国史", "世界史", "朝代", "史书", "左传", "史记", "战国", "国语")
_CHECK_CUES = ("对吗", "对不对", "做对了吗", "答对了吗", "我对了吗", "算对了吗", "写对了吗", "是不是")
_GENERATION_CUES = ("出题", "出几道题", "出十道题", "类似题", "同类型题", "再来几题", "练习题")
_CONCEPT_CUES = ("什么是", "是什么意思", "怎么理解", "为什么", "区别", "定义", "原理")
_SOLVE_CUES = ("怎么做", "咋做", "求", "计算", "证明", "解", "求值", "选哪个", "列式", "判断")


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def _fallback_subject(text: str) -> str:
    if _contains_any(text, _MATH_HINTS):
        return "math"
    if _contains_any(text, _ENGLISH_HINTS):
        return "english"
    if _contains_any(text, _CHINESE_HINTS):
        return "chinese"
    if _contains_any(text, _PHYSICS_HINTS):
        return "physics"
    if _contains_any(text, _HISTORY_HINTS):
        return "history"
    return "unknown"


def _looks_like_problem_statement(text: str) -> bool:
    return bool(
        _contains_any(text, _SOLVE_CUES)
        or _contains_any(text, _MATH_HINTS)
        or ("A(" in text and "B(" in text)
        or ("A." in text and "B." in text)
    )


def _extract_json_payload(raw: str) -> dict[str, Any]:
    text = str(raw or "").strip()
    if not text:
        raise ValueError("empty text understanding response")
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
    text = str(snapshot.user_text or "").strip()
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:20]


def _system_prompt() -> str:
    return (
        "你是当前用户问题理解器。"
        "只分析当前这一轮文本，不参考历史题目，不回答问题本身。"
        "输出一个 JSON 对象，不要输出任何额外文本。"
        "字段必须包含：summary, subject_hint, task_hint, contains_problem_statement, "
        "contains_student_solution, asks_check, asks_generation, asks_concept, education_relevance。"
        "subject_hint 仅可取 math|english|chinese|physics|history|general|unknown。"
        "task_hint 仅可取 solve_problem|check_solution|lesson_context|concept_explain|exercise_generation|unknown。"
        "education_relevance 仅可取 strong|medium|weak。"
    )


def _user_message(snapshot: ContextSnapshot) -> dict[str, Any]:
    return {
        "role": "user",
        "content": [
            {
                "type": "text",
                "text": f"当前用户文本：{snapshot.user_text or '无'}",
            }
        ],
    }


def _fallback(snapshot: ContextSnapshot) -> dict[str, Any]:
    text = str(snapshot.user_text or "").strip()
    subject_hint = _fallback_subject(text)
    asks_check = _contains_any(text, _CHECK_CUES)
    asks_generation = _contains_any(text, _GENERATION_CUES)
    asks_concept = _contains_any(text, _CONCEPT_CUES)
    contains_problem_statement = _looks_like_problem_statement(text)
    task_hint = "unknown"
    if asks_check:
        task_hint = "check_solution"
    elif asks_generation:
        task_hint = "exercise_generation"
    elif asks_concept:
        task_hint = "concept_explain"
    elif contains_problem_statement:
        task_hint = "solve_problem"
    education_relevance = "weak"
    if task_hint != "unknown" or subject_hint != "unknown":
        education_relevance = "strong"
    elif "题" in text or "学习" in text:
        education_relevance = "medium"
    return {
        "summary": text,
        "subject_hint": subject_hint,
        "task_hint": task_hint,
        "contains_problem_statement": contains_problem_statement,
        "contains_student_solution": False,
        "asks_check": asks_check,
        "asks_generation": asks_generation,
        "asks_concept": asks_concept,
        "education_relevance": education_relevance,
    }


def resolve_router_text_brief(
    snapshot: ContextSnapshot,
    *,
    timeout: int,
    turn_id: int | None = None,
) -> dict[str, Any]:
    text = str(snapshot.user_text or "").strip()
    if not text:
        return {}

    if not (settings.openai_config.api_key and settings.openai_config.api_base and settings.openai_config.intent_model):
        return _fallback(snapshot)

    cache_key = _cache_key(snapshot)
    cached = _TEXT_BRIEF_CACHE.get(cache_key)
    if cached is not None:
        return cached

    try:
        raw = llm_client.chat(
            api_base=settings.openai_config.api_base,
            api_key=settings.openai_config.api_key,
            model=settings.openai_config.intent_model,
            timeout=min(max(3, timeout), max(4, settings.openai_config.intent_timeout)),
            temperature=0.1,
            modalities=["text"],
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
            "contains_problem_statement": bool(payload.get("contains_problem_statement")),
            "contains_student_solution": bool(payload.get("contains_student_solution")),
            "asks_check": bool(payload.get("asks_check")),
            "asks_generation": bool(payload.get("asks_generation")),
            "asks_concept": bool(payload.get("asks_concept")),
            "education_relevance": str(payload.get("education_relevance") or "weak").strip() or "weak",
        }
    except Exception as exc:
        brief = _fallback(snapshot)
        append_trace_log(
            "router.text_understanding.fallback",
            {
                "error": str(exc),
                "brief": brief,
            },
            turn_id=turn_id,
            scope="router",
        )
        return brief

    if len(_TEXT_BRIEF_CACHE) >= 128:
        _TEXT_BRIEF_CACHE.pop(next(iter(_TEXT_BRIEF_CACHE)))
    _TEXT_BRIEF_CACHE[cache_key] = brief
    append_trace_log(
        "router.text_understanding",
        {
            "brief": brief,
        },
        turn_id=turn_id,
        scope="router",
    )
    return brief
