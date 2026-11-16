"""端侧视觉分析客户端：调用本地 Qwen2-VL 服务把 image->text，填充会话分析缓存。

路由 / 意图 / 主干共享同一缓存（cached_or_metadata_block_analysis），故只需在 turn
intake 填充一次。失败时返回 None，回退 metadata 分析，保证可用性。
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

_LOG = logging.getLogger(__name__)

VISION_API_BASE = os.getenv("STREAMING_AVA_EDGE_VISION_API_BASE", "http://127.0.0.1:8080/v1")
VISION_TIMEOUT = float(os.getenv("STREAMING_AVA_EDGE_VISION_TIMEOUT", "30"))

_PROMPT = (
    "你是教育场景视觉分析器。观察图片，仅输出一个 JSON 对象，字段："
    'summary(中文一句话描述图片内容), subject_hint(数学/语文/英语/物理/化学/unknown), '
    'task_hint(解题/批改/讲解/问答/unknown), contains_student_work(布尔,是否含学生手写作答), '
    'contains_problem_statement(布尔,是否含题目), education_relevance(high/medium/weak)。'
    "不要输出 JSON 以外的内容。"
)


def _image_source(block: dict[str, Any]) -> str:
    return str(block.get("data_url") or block.get("uri") or block.get("preview_url") or "").strip()


def analyze_blocks(blocks: list[dict[str, Any]]) -> dict[str, Any] | None:
    images = [b for b in blocks if str(b.get("kind", "")) == "input_image" and _image_source(b)]
    if not images:
        return None
    src = _image_source(images[0])
    try:
        import httpx

        payload = {
            "model": "qwen2-vl-2b-local",
            "max_tokens": 256,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": src}},
                        {"type": "text", "text": _PROMPT},
                    ],
                }
            ],
        }
        resp = httpx.post(
            f"{VISION_API_BASE}/chat/completions",
            json=payload,
            timeout=VISION_TIMEOUT,
            trust_env=False,
        )
        resp.raise_for_status()
        text = str(resp.json()["choices"][0]["message"]["content"] or "").strip()
    except Exception as exc:
        _LOG.warning("edge vision analyze failed: %s", exc)
        return None

    analysis: dict[str, Any] = {}
    try:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            analysis = json.loads(text[start : end + 1])
    except Exception:
        analysis = {}
    summary = str(analysis.get("summary") or text or "").strip()[:200]
    return {
        "summary": summary,
        "question_summary": summary,
        "subject_hint": str(analysis.get("subject_hint") or "unknown"),
        "task_hint": str(analysis.get("task_hint") or "unknown"),
        "contains_student_work": bool(analysis.get("contains_student_work")),
        "contains_lesson_context": bool(analysis.get("contains_lesson_context")),
        "contains_sub_problem": bool(analysis.get("contains_sub_problem")),
        "contains_problem_statement": bool(analysis.get("contains_problem_statement")),
        "education_relevance": str(analysis.get("education_relevance") or "medium"),
        "followup_requires_visual_reread": bool(analysis.get("contains_student_work")),
        "confidence": 0.8,
        "source": "edge_vlm",
    }


def ensure_visual_analysis(memory: Any, blocks: list[dict[str, Any]]) -> None:
    if not blocks:
        return
    if memory.cached_block_analysis(blocks):
        return
    analysis = analyze_blocks(blocks)
    if analysis:
        memory.remember_block_analysis(blocks, analysis)