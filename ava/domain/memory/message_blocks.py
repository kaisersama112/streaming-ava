"""消息内容块分析缓存。"""

from __future__ import annotations

import hashlib
from typing import Any


class MessageBlockMemoryStore:
    def __init__(self) -> None:
        self._cache: dict[str, dict[str, Any]] = {}

    @property
    def cache(self) -> dict[str, dict[str, Any]]:
        return {key: dict(value) for key, value in self._cache.items()}

    def reset(self) -> None:
        self._cache = {}

    def load_payload(self, payload: dict[str, Any] | None) -> None:
        normalized: dict[str, dict[str, Any]] = {}
        for key, value in dict(payload or {}).items():
            cache_key = str(key or "").strip()
            if not cache_key or not isinstance(value, dict):
                continue
            normalized[cache_key] = {str(item_key): item_value for item_key, item_value in value.items()}
        self._cache = normalized

    def to_payload(self) -> dict[str, dict[str, Any]]:
        return self.cache

    @staticmethod
    def _block_source_token(block: dict[str, Any]) -> str:
        ref = block.get("data_url") or block.get("uri") or block.get("name") or ""
        kind = str(block.get("kind", "") or "")
        name = str(block.get("name", "") or "")
        summary = str(block.get("summary", "") or "")
        digest = hashlib.sha256(str(ref).encode("utf-8", errors="ignore")).hexdigest()[:16]
        return f"{kind}:{name}:{digest}:{summary[:32]}"

    def block_bundle_key(
        self,
        message_blocks: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    ) -> str:
        parts = [self._block_source_token(block) for block in list(message_blocks or [])]
        return "|".join(parts[:4])

    @staticmethod
    def _truncate_text(value: str, limit: int) -> str:
        text = str(value or "").strip()
        if len(text) <= limit:
            return text
        return text[:limit].rstrip() + "..."

    def metadata_block_analysis(
        self,
        message_blocks: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    ) -> dict[str, Any]:
        items = list(message_blocks or [])
        if not items:
            return {}
        first = items[0]
        metadata = dict(first.get("metadata") or {})
        return {
            "summary": self._truncate_text(str(first.get("summary") or first.get("name") or "附件"), 120),
            "question_summary": self._truncate_text(str(first.get("summary") or first.get("name") or "附件"), 120),
            "subject_hint": str(metadata.get("subject_hint") or "unknown").strip() or "unknown",
            "task_hint": str(metadata.get("task_hint") or "unknown").strip() or "unknown",
            "contains_student_work": bool(metadata.get("contains_student_work")),
            "contains_lesson_context": bool(metadata.get("contains_lesson_context")),
            "contains_sub_problem": bool(metadata.get("contains_sub_problem")),
            "contains_problem_statement": bool(metadata.get("contains_problem_statement")),
            "education_relevance": (
                "medium"
                if metadata.get("message_block_role") in {"problem_material", "answer_sheet", "lesson_clip"}
                else "weak"
            ),
            "followup_requires_visual_reread": bool(metadata.get("contains_student_work")),
            "confidence": 0.45,
            "source": "metadata",
        }

    def cached_block_analysis(
        self,
        message_blocks: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    ) -> dict[str, Any]:
        cache_key = self.block_bundle_key(message_blocks)
        if not cache_key:
            return {}
        cached = self._cache.get(cache_key)
        if cached:
            return dict(cached)
        return {}

    def cached_or_metadata_block_analysis(
        self,
        message_blocks: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    ) -> dict[str, Any]:
        cached = self.cached_block_analysis(message_blocks)
        if cached:
            return cached
        return self.metadata_block_analysis(message_blocks)

    def remember_block_analysis(
        self,
        message_blocks: list[dict[str, Any]] | tuple[dict[str, Any], ...],
        analysis: dict[str, Any],
    ) -> None:
        cache_key = self.block_bundle_key(message_blocks)
        if not cache_key or not analysis:
            return
        if len(self._cache) >= 64 and cache_key not in self._cache:
            oldest_key = next(iter(self._cache))
            self._cache.pop(oldest_key, None)
        self._cache[cache_key] = {str(key): value for key, value in dict(analysis or {}).items()}

