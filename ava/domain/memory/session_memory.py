"""Dedicated session memory model separated from the route/state machine."""

from __future__ import annotations

import hashlib
import re
from collections import deque
from typing import Any, Callable

from ava.domain.multimodal import MediaArtifact, TurnInput
from ava.domain.conversation.summary import summarize_history


class SessionMemory:
    """Persisted memory slots and continuity metadata for a session."""

    def __init__(self, memory_size: int = 8) -> None:
        self.memory_size = max(1, int(memory_size or 8))
        self.reset()

    @staticmethod
    def empty_education_state() -> dict[str, Any]:
        return {
            "subject": "",
            "knowledge_point": "",
            "stage": "",
            "last_problem": "",
            "level": "",
            "learning_scenario": "",
            "learning_objects": [],
            "object_scope": "",
            "object_continuity": "",
            "primary_action": "",
            "secondary_actions": [],
            "answer_boundary": "",
            "previous_branch": "",
            "previous_strategy_id": "",
            "previous_policy_id": "",
            "previous_strategy_state": {},
        }

    def reset(self) -> None:
        self.facts: dict[str, str] = {}
        self.recent_topics: deque[str] = deque(maxlen=self.memory_size)
        self.context_summary: str = "无"
        self.multimodal_context_summary: str = "无"
        self.artifact_analysis_cache: dict[str, dict[str, Any]] = {}
        self.education_state: dict[str, Any] = self.empty_education_state()

    def to_payload(
        self,
        *,
        history: list[dict[str, Any]],
        turn_records: list[dict[str, Any]],
        summarize_turn_records: Callable[[list[dict[str, Any]]], str],
    ) -> dict[str, Any]:
        return {
            "facts": dict(self.facts),
            "recent_topics": list(self.recent_topics),
            "context_summary": summarize_history(history[-(self.memory_size * 2) :]),
            "multimodal_context_summary": summarize_turn_records(turn_records[-self.memory_size :]),
            "artifact_analysis_cache": dict(self.artifact_analysis_cache),
            "education_state": dict(self.education_state),
        }

    def load_payload(
        self,
        data: dict[str, Any],
        *,
        history: list[dict[str, Any]],
        turn_records: list[dict[str, Any]],
        summarize_turn_records: Callable[[list[dict[str, Any]]], str],
    ) -> None:
        payload = data.get("memory")
        memory_payload = dict(payload) if isinstance(payload, dict) else {}

        self.facts = {
            str(key): str(value)
            for key, value in dict(memory_payload.get("facts") or {}).items()
            if str(key).strip() and value not in (None, "")
        }
        self.recent_topics = deque(
            [str(item) for item in (memory_payload.get("recent_topics") or []) if str(item).strip()],
            maxlen=self.memory_size,
        )
        self.context_summary = summarize_history(history[-(self.memory_size * 2) :])
        self.multimodal_context_summary = summarize_turn_records(turn_records[-self.memory_size :])
        self.artifact_analysis_cache = self.normalize_artifact_analysis_cache(memory_payload.get("artifact_analysis_cache") or {})
        base_education_state = self.empty_education_state()
        base_education_state.update(dict(memory_payload.get("education_state") or {}))
        self.education_state = base_education_state

    def refresh_summaries(
        self,
        *,
        history: list[dict[str, Any]],
        turn_records: list[dict[str, Any]],
        summarize_turn_records: Callable[[list[dict[str, Any]]], str],
    ) -> None:
        self.context_summary = summarize_history(history[-(self.memory_size * 2) :])
        self.multimodal_context_summary = summarize_turn_records(turn_records[-self.memory_size :])

    def update_fact_slots(self, user_text: str) -> None:
        patterns = [
            (r"我叫([\u4e00-\u9fa5A-Za-z0-9_]{1,20})", "name"),
            (r"我是([\u4e00-\u9fa5A-Za-z0-9_]{1,20})", "identity"),
            (r"我在([\u4e00-\u9fa5A-Za-z0-9_]{1,20})", "location"),
            (r"我喜欢([\u4e00-\u9fa5A-Za-z0-9_]{1,30})", "likes"),
            (r"我讨厌([\u4e00-\u9fa5A-Za-z0-9_]{1,30})", "dislikes"),
        ]
        for pattern, slot in patterns:
            match = re.search(pattern, user_text)
            if match:
                self.facts[slot] = match.group(1)

    def apply_route_transition(self, *, should_preserve_teaching_state: bool) -> None:
        if not should_preserve_teaching_state:
            self.education_state = self.empty_education_state()

    def update_education_state_from_text(self, user_text: str) -> None:
        match_subject = re.search(r"(数学|语文|英语|物理|化学|生物|历史|地理|政治)", user_text)
        if match_subject:
            self.education_state["subject"] = match_subject.group(1)
        match_point = re.search(
            r"(?:讲解|解释|学习|复习|辅导|讲题|知识点是|关于)([\u4e00-\u9fa5A-Za-z0-9_、，,（）()\-]{2,30})",
            user_text,
        )
        if "知识点" in user_text and not match_point:
            self.education_state["knowledge_point"] = user_text[:30]
        elif match_point:
            self.education_state["knowledge_point"] = match_point.group(1).strip("：:，,。 ")

        if any(keyword in user_text for keyword in ["讲解", "解释", "思路", "为什么"]):
            self.education_state["stage"] = "讲解"
        if any(keyword in user_text for keyword in ["练习", "做题", "题目"]):
            self.education_state["stage"] = "练习"
            self.education_state["last_problem"] = user_text[:40]

    def update_education_state_from_strategy(
        self,
        strategy: dict[str, Any] | None,
        *,
        turn_input: TurnInput | None = None,
    ) -> None:
        if not strategy:
            return

        analysis = dict(strategy.get("analysis") or {})
        frame = dict(analysis.get("education_turn_frame") or analysis.get("task_frame") or {})
        scenario_policy = dict(frame.get("scenario_policy") or {})

        subject = str(
            strategy.get("subject")
            or analysis.get("subject_axis")
            or analysis.get("subject")
            or self.education_state.get("subject")
            or ""
        ).strip()
        if subject:
            self.education_state["subject"] = subject

        learning_scenario = str(frame.get("primary_scenario") or analysis.get("primary_scenario") or "").strip()
        primary_action = str(frame.get("primary_action") or analysis.get("primary_action") or "").strip()
        object_scope = str(frame.get("object_scope") or analysis.get("object_scope") or "").strip()
        object_continuity = str(frame.get("object_continuity") or analysis.get("object_continuity") or "").strip()
        learning_objects = [
            str(item).strip()
            for item in (frame.get("learning_objects") or analysis.get("learning_objects") or [])
            if str(item).strip()
        ]
        secondary_actions = [
            str(item).strip()
            for item in (frame.get("secondary_actions") or [])
            if str(item).strip()
        ]
        answer_boundary = str(scenario_policy.get("answer_boundary") or analysis.get("answer_boundary") or "").strip()

        if learning_scenario:
            self.education_state["learning_scenario"] = learning_scenario
            self.education_state["stage"] = "练习" if learning_scenario == "practice" else "讲解"
        if learning_objects:
            self.education_state["learning_objects"] = learning_objects
        if object_scope:
            self.education_state["object_scope"] = object_scope
        if object_continuity:
            self.education_state["object_continuity"] = object_continuity
        if primary_action:
            self.education_state["primary_action"] = primary_action
        self.education_state["secondary_actions"] = secondary_actions
        if answer_boundary:
            self.education_state["answer_boundary"] = answer_boundary

        knowledge_point = str(analysis.get("knowledge_point") or self.education_state.get("knowledge_point") or "").strip()
        if knowledge_point:
            self.education_state["knowledge_point"] = knowledge_point

        if turn_input is not None and "problem" in set(learning_objects):
            current_problem = turn_input.normalized_text() or turn_input.multimodal_summary()
            if current_problem:
                self.education_state["last_problem"] = current_problem[:80]

        branch = str(strategy.get("branch") or "").strip()
        strategy_id = str(strategy.get("strategy_id") or "").strip()
        policy_id = str(strategy.get("policy_id") or analysis.get("selected_policy_id") or "").strip()
        previous_state = {
            "previous_branch": branch,
            "previous_strategy_id": strategy_id,
            "previous_policy_id": policy_id,
            "previous_subject": subject,
            "previous_primary_scenario": learning_scenario,
            "previous_primary_action": primary_action,
            "previous_learning_objects": learning_objects,
            "previous_object_scope": object_scope,
            "previous_object_continuity": object_continuity,
            "previous_answer_boundary": answer_boundary,
        }
        self.education_state["previous_branch"] = branch
        self.education_state["previous_strategy_id"] = strategy_id
        self.education_state["previous_policy_id"] = policy_id
        self.education_state["previous_strategy_state"] = previous_state

    @staticmethod
    def normalize_artifact_analysis_cache(cache: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
        normalized: dict[str, dict[str, Any]] = {}
        for key, value in dict(cache or {}).items():
            cache_key = str(key or "").strip()
            if not cache_key or not isinstance(value, dict):
                continue
            normalized[cache_key] = {str(item_key): item_value for item_key, item_value in value.items()}
        return normalized

    @staticmethod
    def _artifact_source_token(artifact: MediaArtifact | dict[str, Any]) -> str:
        if isinstance(artifact, MediaArtifact):
            ref = artifact.data_url or artifact.uri or artifact.name
            kind = artifact.kind
            name = artifact.name
            summary = artifact.summary
        else:
            ref = artifact.get("data_url") or artifact.get("uri") or artifact.get("name") or ""
            kind = str(artifact.get("kind", "") or "")
            name = str(artifact.get("name", "") or "")
            summary = str(artifact.get("summary", "") or "")
        digest = hashlib.sha256(str(ref).encode("utf-8", errors="ignore")).hexdigest()[:16]
        return f"{kind}:{name}:{digest}:{summary[:32]}"

    def artifact_bundle_key(
        self,
        artifacts: tuple[MediaArtifact, ...] | list[MediaArtifact] | list[dict[str, Any]],
    ) -> str:
        parts = [self._artifact_source_token(artifact) for artifact in list(artifacts or [])]
        return "|".join(parts[:4])

    @staticmethod
    def _truncate_text(value: str, limit: int) -> str:
        text = str(value or "").strip()
        if len(text) <= limit:
            return text
        return text[:limit].rstrip() + "..."

    def _metadata_artifact_analysis(self, artifacts: tuple[MediaArtifact, ...] | list[MediaArtifact]) -> dict[str, Any]:
        items = list(artifacts or [])
        if not items:
            return {}
        first = items[0]
        metadata = dict(first.metadata or {})
        return {
            "summary": self._truncate_text(first.summary or first.name or "附件内容", 120),
            "question_summary": self._truncate_text(first.summary or first.name or "附件内容", 120),
            "subject_hint": str(metadata.get("subject_hint") or "unknown").strip() or "unknown",
            "task_hint": str(metadata.get("task_hint") or "unknown").strip() or "unknown",
            "contains_student_work": bool(metadata.get("contains_student_work")),
            "contains_lesson_context": bool(metadata.get("contains_lesson_context")),
            "contains_sub_problem": bool(metadata.get("contains_sub_problem")),
            "contains_problem_statement": bool(metadata.get("contains_problem_statement")),
            "education_relevance": "medium" if metadata.get("artifact_role") in {"problem_material", "answer_sheet", "lesson_clip"} else "weak",
            "followup_requires_visual_reread": bool(metadata.get("contains_student_work")),
            "confidence": 0.45,
            "source": "metadata",
        }

    def cached_artifact_analysis(
        self,
        artifacts: tuple[MediaArtifact, ...] | list[MediaArtifact],
    ) -> dict[str, Any]:
        cache_key = self.artifact_bundle_key(artifacts)
        if not cache_key:
            return {}
        cached = self.artifact_analysis_cache.get(cache_key)
        if cached:
            return dict(cached)
        return {}

    def cached_or_metadata_artifact_analysis(
        self,
        artifacts: tuple[MediaArtifact, ...] | list[MediaArtifact],
    ) -> dict[str, Any]:
        cached = self.cached_artifact_analysis(artifacts)
        if cached:
            return cached
        return self._metadata_artifact_analysis(artifacts)

    def remember_artifact_analysis(
        self,
        artifacts: tuple[MediaArtifact, ...] | list[MediaArtifact],
        analysis: dict[str, Any],
    ) -> None:
        cache_key = self.artifact_bundle_key(artifacts)
        if not cache_key or not analysis:
            return
        if len(self.artifact_analysis_cache) >= 64 and cache_key not in self.artifact_analysis_cache:
            oldest_key = next(iter(self.artifact_analysis_cache))
            self.artifact_analysis_cache.pop(oldest_key, None)
        self.artifact_analysis_cache[cache_key] = {
            str(key): value for key, value in dict(analysis or {}).items()
        }

    def to_debug_payload(self) -> dict[str, Any]:
        return {
            "facts": dict(self.facts),
            "recent_topics": list(self.recent_topics),
            "context_summary": self.context_summary,
            "multimodal_context_summary": self.multimodal_context_summary,
            "education_state": dict(self.education_state),
            "artifact_analysis_cache_size": len(self.artifact_analysis_cache),
        }
