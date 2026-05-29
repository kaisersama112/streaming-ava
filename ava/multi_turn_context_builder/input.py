"""输入装配模块。

负责把展示层传入的原始文本、附件数据装配成统一的 `TurnInput`。
这里是 `context_engine` 的输入边界，主要职责包括：
- 定义展示层附件载荷 `AttachmentPayload`
- 推断附件相关的学科/任务提示信息
- 把附件转换为 `MediaArtifact`
- 把文本与附件统一装配为 `TurnInput`
"""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from typing import Iterable

from ava.domain.multimodal import MediaArtifact, TurnInput


@dataclass(frozen=True)
class AttachmentPayload:
    """展示层采集到的原始附件载荷。"""

    name: str
    mime_type: str
    data: bytes
    summary: str = ""
    uri: str | None = None


class TurnInputAssembler:
    """负责把原始输入装配成统一 `TurnInput` 的输入装配器。"""

    _MATH_HINTS = ("数学", "函数", "几何", "方程", "极限", "导数", "数列", "解析", "三角形", "坐标")
    _ENGLISH_HINTS = ("英语", "英文", "单词", "句子", "语法", "完形", "阅读", "翻译", "a.", "b.", "c.", "d.")
    _CHINESE_HINTS = ("语文", "作文", "文言文", "阅读理解", "病句", "修辞", "古诗")
    _PHYSICS_HINTS = ("物理", "实验", "电路", "受力", "电流", "电压", "滑轮", "杠杆")
    _HISTORY_HINTS = ("历史", "朝代", "史记", "左传", "战国", "古代史", "中国史", "世界史")

    _LESSON_HINTS = ("课堂", "课上", "课程", "老师讲", "视频片段", "这一段", "例题讲解", "lesson")
    _STUDENT_SOLUTION_HINTS = ("学生作答", "学生答案", "我的答案", "我的解答", "我做的", "草稿", "列式", "演算", "步骤")
    _PROBLEM_HINTS = ("题目", "这道题", "题", "选择题", "填空题", "解答题", "例题", "problem")
    _SUB_PROBLEM_HINTS = ("第一小问", "第二小问", "第三小问", "第一问", "第二问", "第三问", "小问")
    _CONCEPT_HINTS = ("知识点", "概念", "定义", "原理", "讲义", "总结")

    def build(
        self,
        text: str | None = None,
        attachments: Iterable[AttachmentPayload] | None = None,
        source: str = "web",
    ) -> TurnInput:
        """把原始文本与附件装配为统一 `TurnInput`。"""

        artifacts = [self._build_artifact(attachment) for attachment in attachments or ()]
        return TurnInput(text=text or "", artifacts=tuple(artifacts), source=source)

    def _build_artifact(self, attachment: AttachmentPayload) -> MediaArtifact:
        kind = self._detect_artifact_kind(attachment.mime_type)
        return MediaArtifact(
            kind=kind,
            name=attachment.name,
            mime_type=attachment.mime_type,
            summary=attachment.summary,
            data_url=self._to_data_url(attachment.mime_type, attachment.data) if kind in {"image", "audio", "video"} else None,
            uri=attachment.uri,
            metadata={
                **self._build_artifact_metadata(
                    name=attachment.name,
                    summary=attachment.summary,
                    kind=kind,
                ),
                "size_bytes": len(attachment.data),
            },
        )

    @staticmethod
    def _detect_artifact_kind(mime_type: str) -> str:
        if mime_type.startswith("image/"):
            return "image"
        if mime_type.startswith("audio/"):
            return "audio"
        if mime_type.startswith("video/"):
            return "video"
        return "file"

    @staticmethod
    def _to_data_url(mime_type: str, data: bytes) -> str:
        encoded = base64.b64encode(data).decode("ascii")
        return f"data:{mime_type};base64,{encoded}"

    def _build_artifact_metadata(self, *, name: str, summary: str, kind: str) -> dict[str, object]:
        evidence_text = " ".join(part for part in (name, summary) if part).strip().lower()
        has_student_solution = self._contains_any(evidence_text, self._STUDENT_SOLUTION_HINTS)
        has_lesson_context = self._contains_any(evidence_text, self._LESSON_HINTS)
        return {
            "size_bytes": 0,
            "artifact_role": self._artifact_role(
                kind,
                evidence_text,
                has_student_solution=has_student_solution,
                has_lesson_context=has_lesson_context,
            ),
            "subject_hint": self._subject_hint(evidence_text),
            "task_hint": self._task_hint(
                evidence_text,
                has_student_solution=has_student_solution,
                has_lesson_context=has_lesson_context,
            ),
            "ocr_text": summary.strip(),
            "contains_student_work": has_student_solution,
            "contains_lesson_context": has_lesson_context,
            "contains_sub_problem": self._contains_any(evidence_text, self._SUB_PROBLEM_HINTS),
            "contains_problem_statement": self._contains_any(evidence_text, self._PROBLEM_HINTS),
            "problem_count_hint": self._problem_count_hint(evidence_text),
        }

    @staticmethod
    def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
        return any(keyword.lower() in text for keyword in keywords)

    def _subject_hint(self, text: str) -> str:
        if self._contains_any(text, self._MATH_HINTS):
            return "math"
        if self._contains_any(text, self._ENGLISH_HINTS):
            return "english"
        if self._contains_any(text, self._CHINESE_HINTS):
            return "chinese"
        if self._contains_any(text, self._PHYSICS_HINTS):
            return "physics"
        if self._contains_any(text, self._HISTORY_HINTS):
            return "history"
        return ""

    def _task_hint(self, text: str, *, has_student_solution: bool, has_lesson_context: bool) -> str:
        if has_student_solution:
            return "check_solution"
        if self._contains_any(text, self._SUB_PROBLEM_HINTS):
            return "solve_sub_problem"
        if has_lesson_context:
            return "lesson_explain"
        if self._contains_any(text, self._CONCEPT_HINTS):
            return "concept_explain"
        if self._contains_any(text, self._PROBLEM_HINTS):
            return "solve_problem"
        return ""

    def _artifact_role(self, kind: str, text: str, *, has_student_solution: bool, has_lesson_context: bool) -> str:
        if has_student_solution:
            return "answer_sheet"
        if kind == "video" and has_lesson_context:
            return "lesson_clip"
        if self._contains_any(text, self._CONCEPT_HINTS):
            return "concept_material"
        if self._contains_any(text, self._PROBLEM_HINTS) or kind == "image":
            return "problem_material"
        return "generic_attachment"

    @staticmethod
    def _problem_count_hint(text: str) -> int:
        matched_sections = re.findall(r"第[一二三四五六七八九十0-9]+[问小问]", text)
        if matched_sections:
            return len(matched_sections)
        numbered_items = re.findall(r"\b[1-9][\.\)]", text)
        return len(numbered_items)
