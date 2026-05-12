"""Application helpers for constructing multimodal turn inputs."""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from typing import Iterable

from ava.domain.multimodal import MediaArtifact, TurnInput


@dataclass(frozen=True)
class AttachmentPayload:
    """Raw attachment payload captured by a presentation layer."""

    name: str
    mime_type: str
    data: bytes
    summary: str = ""
    uri: str | None = None


_MATH_HINTS = ("数学", "函数", "几何", "方程", "极限", "导数", "数列", "解析式", "三角形", "坐标")
_ENGLISH_HINTS = ("英语", "英文", "单词", "句子", "语法", "完形", "阅读", "翻译", "A.", "B.", "C.", "D.")
_CHINESE_HINTS = ("语文", "作文", "文言文", "阅读理解", "病句", "修辞", "古诗")
_PHYSICS_HINTS = ("物理", "实验", "电路", "受力", "电流", "电压", "滑轮", "杠杆")
_HISTORY_HINTS = ("历史", "朝代", "史记", "左传", "战国", "古代史", "中国史", "世界史")
_LESSON_HINTS = ("课堂", "课上", "课程", "老师讲", "视频片段", "这一段", "例题讲解", "lesson")
_STUDENT_SOLUTION_HINTS = ("学生作答", "学生答案", "我的答案", "我的解答", "我做的", "草稿", "列式", "演算", "步骤")
_PROBLEM_HINTS = ("题目", "这道题", "求", "选择题", "填空题", "解答题", "例题", "problem")
_SUB_PROBLEM_HINTS = ("第一小问", "第二小问", "第三小问", "第一问", "第二问", "第1问", "第2问", "小问")
_CONCEPT_HINTS = ("知识点", "概念", "定义", "原理", "讲义", "总结")


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword.lower() in text for keyword in keywords)


def _subject_hint(text: str) -> str:
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
    return ""


def _task_hint(text: str, *, has_student_solution: bool, has_lesson_context: bool) -> str:
    if has_student_solution:
        return "check_solution"
    if _contains_any(text, _SUB_PROBLEM_HINTS):
        return "solve_sub_problem"
    if has_lesson_context:
        return "lesson_explain"
    if _contains_any(text, _CONCEPT_HINTS):
        return "concept_explain"
    if _contains_any(text, _PROBLEM_HINTS):
        return "solve_problem"
    return ""


def _artifact_role(kind: str, text: str, *, has_student_solution: bool, has_lesson_context: bool) -> str:
    if has_student_solution:
        return "answer_sheet"
    if kind == "video" and has_lesson_context:
        return "lesson_clip"
    if _contains_any(text, _CONCEPT_HINTS):
        return "concept_material"
    if _contains_any(text, _PROBLEM_HINTS) or kind == "image":
        return "problem_material"
    return "generic_attachment"


def _problem_count_hint(text: str) -> int:
    counts = re.findall(r"第[一二三四五六七八九十0-9]+[问小问]", text)
    if counts:
        return len(counts)
    numbered = re.findall(r"\b[1-9][\.\)]", text)
    return len(numbered)


def _artifact_metadata(name: str, mime_type: str, summary: str, *, kind: str) -> dict[str, object]:
    evidence_text = " ".join(part for part in (name, summary) if part).strip().lower()
    student_solution = _contains_any(evidence_text, _STUDENT_SOLUTION_HINTS)
    lesson_context = _contains_any(evidence_text, _LESSON_HINTS)
    task_hint = _task_hint(evidence_text, has_student_solution=student_solution, has_lesson_context=lesson_context)
    role = _artifact_role(kind, evidence_text, has_student_solution=student_solution, has_lesson_context=lesson_context)
    metadata: dict[str, object] = {
        "size_bytes": 0,
        "artifact_role": role,
        "subject_hint": _subject_hint(evidence_text),
        "task_hint": task_hint,
        "ocr_text": summary.strip(),
        "contains_student_work": student_solution,
        "contains_lesson_context": lesson_context,
        "contains_sub_problem": _contains_any(evidence_text, _SUB_PROBLEM_HINTS),
        "contains_problem_statement": _contains_any(evidence_text, _PROBLEM_HINTS),
        "problem_count_hint": _problem_count_hint(evidence_text),
    }
    return metadata


def _to_data_url(mime_type: str, data: bytes) -> str:
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def build_turn_input(
    text: str | None = None,
    attachments: Iterable[AttachmentPayload] | None = None,
    source: str = "web",
) -> TurnInput:
    artifacts: list[MediaArtifact] = []
    for attachment in attachments or ():
        if attachment.mime_type.startswith("image/"):
            kind = "image"
        elif attachment.mime_type.startswith("audio/"):
            kind = "audio"
        elif attachment.mime_type.startswith("video/"):
            kind = "video"
        else:
            kind = "file"
        artifacts.append(
            MediaArtifact(
                kind=kind,
                name=attachment.name,
                mime_type=attachment.mime_type,
                summary=attachment.summary,
                data_url=_to_data_url(attachment.mime_type, attachment.data) if kind in {"image", "audio", "video"} else None,
                uri=attachment.uri,
                metadata={
                    **_artifact_metadata(
                        attachment.name,
                        attachment.mime_type,
                        attachment.summary,
                        kind=kind,
                    ),
                    "size_bytes": len(attachment.data),
                },
            )
        )

    return TurnInput(text=text or "", artifacts=tuple(artifacts), source=source)
