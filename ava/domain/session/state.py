"""Domain model for persisted conversation/session state."""

from __future__ import annotations

import json
import re
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any

from ava.domain.context import MediaArtifact, TurnInput
from ava.domain.context.summary import summarize_history


class ConversationState:
    """Mutable session aggregate persisted across turns."""

    _DEFAULT_SESSION_ID = "default"
    _SESSION_CONTAINER_KEY = "sessions"
    _INLINE_REFERENCE_TURNS = 2
    _INLINE_REFERENCE_MAX_BYTES = 1_500_000

    def __init__(self, state_file: Path, memory_size: int = 8, session_id: str = _DEFAULT_SESSION_ID) -> None:
        self.state_file = state_file
        self.memory_size = memory_size
        self.session_id = self.normalize_session_id(session_id)
        self.facts: dict[str, str] = {}
        self.intent_counter: dict[str, int] = {}
        self.turn_count: int = 0
        self.recent_topics: deque[str] = deque(maxlen=memory_size)
        self.history: list[dict[str, Any]] = []
        self.turn_records: list[dict[str, Any]] = []
        self.context_summary: str = "无"
        self.multimodal_context_summary: str = "无"
        self.session_scene: str = "general"
        self.turn_scene: str = "general_qa"

        self.education_state: dict[str, Any] = self._empty_education_state()

    @classmethod
    def normalize_session_id(cls, session_id: str | None) -> str:
        normalized = str(session_id or "").strip()
        if not normalized:
            return cls._DEFAULT_SESSION_ID
        normalized = re.sub(r"[^\w\-.:]", "_", normalized)
        return normalized[:64] or cls._DEFAULT_SESSION_ID

    def _empty_education_state(self) -> dict[str, Any]:
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

    def _reset_fields(self) -> None:
        self.facts = {}
        self.intent_counter = {}
        self.turn_count = 0
        self.recent_topics = deque(maxlen=self.memory_size)
        self.history = []
        self.turn_records = []
        self.context_summary = "无"
        self.multimodal_context_summary = "无"
        self.session_scene = "general"
        self.turn_scene = "general_qa"
        self.education_state = self._empty_education_state()

    def _session_payload(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "facts": self.facts,
            "intent_counter": self.intent_counter,
            "turn_count": self.turn_count,
            "recent_topics": list(self.recent_topics),
            "history": self.history[-40:],
            "turn_records": self._serialize_turn_records_for_save(self.turn_records[-40:]),
            "context_summary": summarize_history(self.history[-(self.memory_size * 2) :]),
            "multimodal_context_summary": self._summarize_turn_records(self.turn_records[-self.memory_size :]),
            "session_scene": self.session_scene,
            "turn_scene": self.turn_scene,
            "education_state": self.education_state,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }

    @staticmethod
    def _assistant_context_text(record: dict[str, Any]) -> str:
        turn_status = str(record.get("turn_status", "completed") or "completed").strip()
        assistant_text = str(record.get("assistant_text", "") or "").strip()
        if turn_status == "completed":
            return assistant_text
        return ""

    @staticmethod
    def _compact_strategy_payload(strategy: dict[str, Any] | None) -> dict[str, Any]:
        if not strategy:
            return {}
        analysis = dict((strategy or {}).get("analysis") or {})
        frame = dict(analysis.get("education_turn_frame") or analysis.get("task_frame") or {})
        scenario_policy = dict(frame.get("scenario_policy") or {})
        compact_analysis: dict[str, Any] = {}
        for key in (
            "subject",
            "subject_axis",
            "primary_scenario",
            "primary_action",
            "learning_objects",
            "object_scope",
            "object_continuity",
            "answer_boundary",
            "current_turn_is_followup",
            "current_object_continues",
            "explicit_topic_switch",
            "artifact_subject_hint",
            "artifact_task_hint",
            "prompt_context_policy",
        ):
            value = analysis.get(key)
            if value not in (None, "", [], {}, ()):
                compact_analysis[key] = value
        if frame:
            compact_analysis["education_turn_frame"] = {
                "primary_scenario": frame.get("primary_scenario", ""),
                "learning_objects": frame.get("learning_objects", []),
                "object_scope": frame.get("object_scope", ""),
                "object_continuity": frame.get("object_continuity", ""),
                "primary_action": frame.get("primary_action", ""),
                "secondary_actions": frame.get("secondary_actions", []),
                "scenario_policy": {
                    "preserve_current_scenario": bool(scenario_policy.get("preserve_current_scenario", False)),
                    "allow_scene_switch": bool(scenario_policy.get("allow_scene_switch", False)),
                    "answer_boundary": scenario_policy.get("answer_boundary", ""),
                },
                "domain_hint": frame.get("domain_hint", ""),
                "primary_modality": frame.get("primary_modality", ""),
                "requires_context": bool(frame.get("requires_context", False)),
                "requires_artifact": bool(frame.get("requires_artifact", False)),
                "style_change_only": bool(frame.get("style_change_only", False)),
                "question_kind": frame.get("question_kind", ""),
                "confidence": frame.get("confidence", 0.0),
                "source": frame.get("source", ""),
            }
        continuity = dict(analysis.get("continuity") or {})
        if continuity:
            compact_analysis["continuity"] = {
                "previous_branch": continuity.get("previous_branch", ""),
                "previous_strategy_id": continuity.get("previous_strategy_id", ""),
                "previous_policy_id": continuity.get("previous_policy_id", ""),
                "previous_subject": continuity.get("previous_subject", ""),
                "previous_primary_scenario": continuity.get("previous_primary_scenario", ""),
                "previous_primary_action": continuity.get("previous_primary_action", ""),
                "previous_learning_objects": continuity.get("previous_learning_objects", []),
                "previous_object_scope": continuity.get("previous_object_scope", ""),
                "previous_object_continuity": continuity.get("previous_object_continuity", ""),
                "previous_answer_boundary": continuity.get("previous_answer_boundary", ""),
                "current_turn_is_followup": bool(continuity.get("current_turn_is_followup", False)),
                "followup_confidence": continuity.get("followup_confidence", 0.0),
                "current_object_continues": bool(continuity.get("current_object_continues", False)),
                "same_object_probability": continuity.get("same_object_probability", 0.0),
                "object_continuity": continuity.get("object_continuity", ""),
                "artifact_continuity": continuity.get("artifact_continuity", ""),
                "carry_reference_artifacts": bool(continuity.get("carry_reference_artifacts", False)),
                "allow_fast_path": bool(continuity.get("allow_fast_path", False)),
                "user_requests_style_change_only": bool(continuity.get("user_requests_style_change_only", False)),
                "explicit_topic_switch": bool(continuity.get("explicit_topic_switch", False)),
            }
        compact = {
            "branch": str(strategy.get("branch") or "").strip(),
            "strategy_id": str(strategy.get("strategy_id") or "").strip(),
            "name": str(strategy.get("name") or "").strip(),
            "render_template": str(strategy.get("render_template") or "").strip(),
            "delivery_mode": str(strategy.get("delivery_mode") or "").strip(),
            "ui_mode": str(strategy.get("ui_mode") or "").strip(),
            "policy_id": str(strategy.get("policy_id") or "").strip(),
            "module": str(strategy.get("module") or "").strip(),
            "scene": str(strategy.get("scene") or "").strip(),
            "subject": str(strategy.get("subject") or "").strip(),
            "style": str(strategy.get("style") or "").strip(),
            "source": str(strategy.get("source") or "").strip(),
            "analysis": compact_analysis,
        }
        return {key: value for key, value in compact.items() if value not in (None, "", [], {}, ())}

    @staticmethod
    def _compact_evaluation_payload(evaluation: dict[str, Any] | None) -> dict[str, Any]:
        if not evaluation:
            return {}
        compact: dict[str, Any] = {}
        for key in (
            "branch",
            "session_scene",
            "strategy_id",
            "policy_id",
            "module",
            "subject",
            "style",
            "render_template",
            "delivery_mode",
            "ui_mode",
            "user_followup_type",
            "input_modalities",
            "has_artifacts",
            "intent",
            "route_confidence",
            "turn_result",
        ):
            value = evaluation.get(key)
            if value not in (None, "", [], {}, ()):
                compact[key] = value
        return compact

    def _compact_turn_record(self, record: dict[str, Any]) -> dict[str, Any]:
        copied = dict(record)
        copied["strategy"] = self._compact_strategy_payload(dict(record.get("strategy") or {}))
        copied["evaluation"] = self._compact_evaluation_payload(dict(record.get("evaluation") or {}))
        copied["assistant_text"] = str(record.get("assistant_text", "") or "")
        copied["turn_status"] = str(record.get("turn_status", "completed") or "completed")
        return copied

    def _normalize_loaded_turn_records(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for record in records or []:
            if not isinstance(record, dict):
                continue
            normalized.append(self._compact_turn_record(record))
        return normalized

    def _extract_payload(self, data: dict[str, Any]) -> dict[str, Any]:
        sessions = data.get(self._SESSION_CONTAINER_KEY)
        if isinstance(sessions, dict):
            payload = sessions.get(self.session_id)
            return payload if isinstance(payload, dict) else {}
        return data if isinstance(data, dict) else {}

    def _load_from_payload(self, data: dict[str, Any]) -> None:
        self.facts = data.get("facts", {})
        self.intent_counter = data.get("intent_counter", {})
        self.turn_count = data.get("turn_count", 0)
        self.recent_topics = deque(data.get("recent_topics", []), maxlen=self.memory_size)
        self.history = data.get("history", [])
        self.turn_records = self._normalize_loaded_turn_records(data.get("turn_records", []))
        self.context_summary = summarize_history(self.history[-(self.memory_size * 2) :])
        self.multimodal_context_summary = self._summarize_turn_records(self.turn_records[-self.memory_size :])
        self.session_scene = data.get("session_scene", "general")
        self.turn_scene = data.get("turn_scene", "general_qa")
        self.education_state = data.get("education_state", self._empty_education_state())
        self._normalize_loaded_route_state()
        if not self.turn_records and self.history:
            self.turn_records = self._rebuild_turn_records_from_history(self.history)
            self.multimodal_context_summary = self._summarize_turn_records(self.turn_records[-self.memory_size :])

    def _last_decision_payload_from_turn_records(self) -> tuple[dict[str, Any], dict[str, Any]]:
        for record in reversed(self.turn_records):
            if str(record.get("turn_status", "completed") or "completed").strip() == "pending":
                continue
            decision = record.get("decision")
            strategy = record.get("strategy")
            if isinstance(decision, dict) and any(str(decision.get(key) or "").strip() for key in ("session_scene", "turn_scene")):
                return dict(decision), (dict(strategy) if isinstance(strategy, dict) else {})
        return {}, {}

    def _last_education_strategy_from_turn_records(self) -> dict[str, Any]:
        for record in reversed(self.turn_records):
            if str(record.get("turn_status", "completed") or "completed").strip() == "pending":
                continue
            strategy = record.get("strategy")
            if not isinstance(strategy, dict):
                continue
            branch = str(strategy.get("branch") or "").strip()
            if branch == "education":
                return dict(strategy)
        return {}

    def _normalize_loaded_route_state(self) -> None:
        decision, strategy = self._last_decision_payload_from_turn_records()
        if not decision:
            return

        session_scene = str(decision.get("session_scene") or self.session_scene or "general").strip() or "general"
        turn_scene = str(decision.get("turn_scene") or self.turn_scene or "general_qa").strip() or "general_qa"
        should_preserve_teaching_state = bool(
            decision.get("should_preserve_teaching_state", turn_scene == "education")
        )
        self.apply_route(
            session_scene=session_scene,
            turn_scene=turn_scene,
            should_preserve_teaching_state=should_preserve_teaching_state,
        )
        if (turn_scene == "education" or should_preserve_teaching_state or session_scene == "education") and strategy:
            self.update_education_state_from_strategy(strategy)

    def repair_route_state_from_turn_records(self) -> None:
        decision, latest_strategy = self._last_decision_payload_from_turn_records()
        if not decision:
            return

        session_scene = str(decision.get("session_scene") or self.session_scene or "general").strip() or "general"
        turn_scene = str(decision.get("turn_scene") or self.turn_scene or "general_qa").strip() or "general_qa"
        should_preserve_teaching_state = bool(
            decision.get("should_preserve_teaching_state", turn_scene == "education")
        )
        self.apply_route(
            session_scene=session_scene,
            turn_scene=turn_scene,
            should_preserve_teaching_state=should_preserve_teaching_state,
        )

        if not (turn_scene == "education" or should_preserve_teaching_state or session_scene == "education"):
            return

        strategy = latest_strategy or self._last_education_strategy_from_turn_records()
        if strategy:
            self.update_education_state_from_strategy(strategy)

    def _load_container_for_save(self) -> dict[str, Any]:
        if not self.state_file.exists():
            return {self._SESSION_CONTAINER_KEY: {}}
        try:
            raw = json.loads(self.state_file.read_text(encoding="utf-8"))
        except Exception:
            return {self._SESSION_CONTAINER_KEY: {}}

        if not isinstance(raw, dict):
            return {self._SESSION_CONTAINER_KEY: {}}

        sessions = raw.get(self._SESSION_CONTAINER_KEY)
        if isinstance(sessions, dict):
            return raw

        migrated = dict(raw)
        migrated.pop(self._SESSION_CONTAINER_KEY, None)
        migrated_session_id = self.normalize_session_id(migrated.get("session_id") or self.session_id)
        return {
            self._SESSION_CONTAINER_KEY: {migrated_session_id: migrated},
            "updated_at": raw.get("updated_at", ""),
        }

    def load(self) -> None:
        if not self.state_file.exists():
            return
        try:
            data = json.loads(self.state_file.read_text(encoding="utf-8"))
            payload = self._extract_payload(data)
            if not payload:
                self._reset_fields()
                return
            self._load_from_payload(payload)
        except Exception:
            self._reset_fields()

    def save(self) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        container = self._load_container_for_save()
        sessions = container.get(self._SESSION_CONTAINER_KEY)
        if not isinstance(sessions, dict):
            sessions = {}
            container[self._SESSION_CONTAINER_KEY] = sessions
        sessions[self.session_id] = self._session_payload()
        container["updated_at"] = datetime.now().isoformat(timespec="seconds")
        self.state_file.write_text(json.dumps(container, ensure_ascii=False, indent=2), encoding="utf-8")

    def reset(self) -> None:
        self._reset_fields()

    def _refresh_summaries(self) -> None:
        self.context_summary = summarize_history(self.history[-(self.memory_size * 2) :])
        self.multimodal_context_summary = self._summarize_turn_records(self.turn_records[-self.memory_size :])
        self.save()

    def update_fact_slots(self, user_text: str) -> None:
        """Capture lightweight user facts for personalization."""
        patterns = [
            (r"我叫([\u4e00-\u9fa5A-Za-z0-9_]{1,20})", "name"),
            (r"我是([\u4e00-\u9fa5A-Za-z0-9_]{1,20})", "identity"),
            (r"我在([\u4e00-\u9fa5A-Za-z0-9_]{1,20})", "location"),
            (r"我喜欢([\u4e00-\u9fa5A-Za-z0-9_]{1,30})", "likes"),
            (r"我讨厌([\u4e00-\u9fa5A-Za-z0-9_]{1,30})", "dislikes"),
        ]
        for pattern, slot in patterns:
            m = re.search(pattern, user_text)
            if m:
                self.facts[slot] = m.group(1)

    def apply_route(
        self,
        session_scene: str,
        turn_scene: str,
        should_preserve_teaching_state: bool = True,
    ) -> None:
        """Update scene state and optionally reset teaching progress."""
        self.session_scene = session_scene
        self.turn_scene = turn_scene
        if not should_preserve_teaching_state:
            self.education_state = self._empty_education_state()

    def update_education_state_from_text(self, user_text: str) -> None:
        """Extract coarse teaching metadata from educational utterances."""
        m_subject = re.search(r"(数学|语文|英语|物理|化学|生物|历史|地理|政治)", user_text)
        if m_subject:
            self.education_state["subject"] = m_subject.group(1)
        m_point = re.search(
            r"(?:讲解|解释|学习|复习|辅导|讲题|知识点是|关于)([\u4e00-\u9fa5A-Za-z0-9_、，,（）()\-]{2,30})",
            user_text,
        )
        if "知识点" in user_text and not m_point:
            self.education_state["knowledge_point"] = user_text[:30]
        elif m_point:
            self.education_state["knowledge_point"] = m_point.group(1).strip("：:，,。 ")

        if any(k in user_text for k in ["讲解", "解释", "思路", "为什么"]):
            self.education_state["stage"] = "讲解"
        if any(k in user_text for k in ["练习", "做题", "题目"]):
            self.education_state["stage"] = "练习"
            self.education_state["last_problem"] = user_text[:40]

    def update_education_state_from_strategy(
        self,
        strategy: dict[str, Any] | None,
        *,
        turn_input: TurnInput | None = None,
    ) -> None:
        """Persist structured education frame metadata from the selected strategy."""
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

    def post_turn(self, user_text: str, assistant_text: str, intent: str) -> None:
        """Append turn content and refresh derived summary fields."""
        self.turn_count += 1
        self.intent_counter[intent] = self.intent_counter.get(intent, 0) + 1
        self.recent_topics.append(user_text[:24])
        self.history.append({"role": "user", "content": user_text})
        self.history.append({"role": "assistant", "content": assistant_text})
        self._refresh_summaries()

    def post_multimodal_turn(
        self,
        turn_input: TurnInput,
        assistant_text: str,
        intent: str,
        decision: dict[str, Any],
        strategy: dict[str, Any] | None = None,
        evaluation: dict[str, Any] | None = None,
        turn_status: str = "completed",
    ) -> None:
        """Persist a structured turn record alongside chat history."""
        self.turn_count += 1
        self.intent_counter[intent] = self.intent_counter.get(intent, 0) + 1

        user_history_text = turn_input.history_text()
        self.recent_topics.append(user_history_text[:24])
        self.history.append({"role": "user", "content": user_history_text})
        self.history.append({"role": "assistant", "content": assistant_text})
        self.turn_records.append(
            {
                "role": "turn",
                "source": turn_input.source,
                "user_text": turn_input.normalized_text(),
                "multimodal_summary": turn_input.multimodal_summary(),
                "artifacts": [self._artifact_to_record(artifact) for artifact in turn_input.artifacts],
                "assistant_text": assistant_text,
                "intent": intent,
                "decision": decision,
                "strategy": self._compact_strategy_payload(strategy or {}),
                "evaluation": self._compact_evaluation_payload(evaluation or {}),
                "turn_status": turn_status,
                "created_at": datetime.now().isoformat(timespec="seconds"),
            }
        )
        self._refresh_summaries()

    def upsert_realtime_user_turn(
        self,
        turn_id: int,
        turn_input: TurnInput,
        *,
        refresh_summaries: bool = False,
    ) -> None:
        """Persist the user side of a realtime turn before the assistant finishes.

        This keeps follow-up turns context-aware even when the current reply is
        interrupted or still in flight.
        """
        user_history_text = turn_input.history_text()
        record = next((item for item in reversed(self.turn_records) if item.get("turn_id") == turn_id), None)
        if record is None:
            self.turn_count += 1
            self.recent_topics.append(user_history_text[:24])
            self.history.append({"role": "user", "content": user_history_text, "turn_id": turn_id})
            self.turn_records.append(
                {
                    "role": "turn",
                    "turn_id": turn_id,
                    "source": turn_input.source,
                    "user_text": turn_input.normalized_text(),
                    "multimodal_summary": turn_input.multimodal_summary(),
                    "artifacts": [self._artifact_to_record(artifact) for artifact in turn_input.artifacts],
                    "assistant_text": "",
                    "intent": "",
                    "decision": {},
                    "strategy": {},
                    "evaluation": {},
                    "turn_status": "pending",
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                }
            )
        else:
            record["source"] = turn_input.source
            record["user_text"] = turn_input.normalized_text()
            record["multimodal_summary"] = turn_input.multimodal_summary()
            record["artifacts"] = [self._artifact_to_record(artifact) for artifact in turn_input.artifacts]
            if not any(item.get("role") == "user" and item.get("turn_id") == turn_id for item in self.history):
                self.history.append({"role": "user", "content": user_history_text, "turn_id": turn_id})
        if refresh_summaries:
            self._refresh_summaries()

    def complete_realtime_turn(
        self,
        turn_id: int,
        *,
        turn_input: TurnInput,
        assistant_text: str,
        intent: str,
        decision: dict[str, Any] | None = None,
        strategy: dict[str, Any] | None = None,
        evaluation: dict[str, Any] | None = None,
        turn_status: str = "completed",
        persist: bool = True,
    ) -> None:
        """Finalize a realtime turn previously inserted by upsert_realtime_user_turn."""
        record = next((item for item in reversed(self.turn_records) if item.get("turn_id") == turn_id), None)
        if record is None:
            self.post_multimodal_turn(
                turn_input=turn_input,
                assistant_text=assistant_text,
                intent=intent,
                decision=decision or {},
                strategy=strategy,
                evaluation=evaluation,
                turn_status=turn_status,
            )
            if persist:
                self.save()
            return

        if intent:
            self.intent_counter[intent] = self.intent_counter.get(intent, 0) + 1

        record["assistant_text"] = assistant_text
        record["intent"] = intent
        record["decision"] = decision or {}
        record["strategy"] = self._compact_strategy_payload(strategy or {})
        record["evaluation"] = self._compact_evaluation_payload(evaluation or {})
        record["turn_status"] = turn_status

        decision_payload = dict(decision or {})
        turn_scene = str(decision_payload.get("turn_scene") or self.turn_scene or "").strip()
        session_scene = str(decision_payload.get("session_scene") or self.session_scene or "").strip()
        should_preserve_teaching_state = bool(
            decision_payload.get("should_preserve_teaching_state", turn_scene == "education")
        )
        if turn_scene:
            self.apply_route(
                session_scene=session_scene or self.session_scene,
                turn_scene=turn_scene,
                should_preserve_teaching_state=should_preserve_teaching_state,
            )
        if turn_scene == "education":
            self.update_education_state_from_strategy(strategy or {}, turn_input=turn_input)

        if assistant_text.strip() and turn_status == "completed":
            if not any(item.get("role") == "assistant" and item.get("turn_id") == turn_id for item in self.history):
                self.history.append({"role": "assistant", "content": assistant_text, "turn_id": turn_id})

        self._refresh_summaries()
        if persist:
            self.save()

    def _rebuild_turn_records_from_history(self, history: list[dict[str, Any]]) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        idx = 0
        while idx < len(history):
            user = history[idx]
            assistant = history[idx + 1] if idx + 1 < len(history) else {"role": "assistant", "content": ""}
            if user.get("role") != "user":
                idx += 1
                continue
            user_content = str(user.get("content", ""))
            records.append(
                {
                    "role": "turn",
                    "source": "legacy",
                    "user_text": user_content,
                    "multimodal_summary": user_content,
                    "artifacts": [],
                    "assistant_text": str(assistant.get("content", "")),
                    "intent": "",
                    "decision": {},
                    "created_at": "",
                }
            )
            idx += 2
        return records

    def _summarize_turn_records(self, turn_records: list[dict[str, Any]]) -> str:
        if not turn_records:
            return "无"

        lines: list[str] = []
        for record in turn_records:
            turn_status = str(record.get("turn_status", "completed") or "completed").strip()
            user_text = str(record.get("user_text", "")).strip()
            multimodal_summary = str(record.get("multimodal_summary", "")).strip()
            assistant_text = (
                str(record.get("assistant_text", "")).strip()
                if turn_status == "completed"
                else ""
            )
            label = user_text or multimodal_summary or "无"
            if record.get("artifacts"):
                artifact_labels = []
                for artifact in record.get("artifacts", []):
                    kind = artifact.get("kind", "file")
                    name = artifact.get("name", "")
                    summary = str(artifact.get("summary", "")).strip()
                    if summary:
                        artifact_labels.append(f"[{kind}] {name}: {summary}")
                    else:
                        artifact_labels.append(f"[{kind}] {name}")
                if artifact_labels:
                    label = f"{label}\n附件: {'; '.join(artifact_labels)}"
            if assistant_text:
                assistant_text = assistant_text[:80]
                lines.append(f"用户: {label}\n助手: {assistant_text}")
            else:
                lines.append(f"用户: {label}")
        return "\n".join(lines) if lines else "无"

    def recent_reference_artifacts(
        self,
        *,
        current_turn_id: int | None = None,
        limit_turns: int = 1,
    ) -> tuple[MediaArtifact, ...]:
        if limit_turns <= 0:
            return ()

        collected: list[MediaArtifact] = []
        turns_with_media = 0
        for record in reversed(self.turn_records):
            if current_turn_id is not None and record.get("turn_id") == current_turn_id:
                continue
            raw_artifacts = record.get("artifacts") or []
            media = [
                self._record_to_artifact(item)
                for item in raw_artifacts
                if item.get("kind") in {"image", "audio", "video"} and item.get("data_url")
            ]
            media = [item for item in media if item is not None]
            if not media:
                continue
            collected.extend(media)
            turns_with_media += 1
            if turns_with_media >= limit_turns:
                break
        return tuple(collected)

    @staticmethod
    def _artifact_to_record(artifact) -> dict[str, Any]:
        record = {
            "kind": artifact.kind,
            "name": artifact.name,
            "mime_type": artifact.mime_type,
            "summary": artifact.summary,
            "uri": artifact.uri,
            "metadata": artifact.metadata,
        }
        size_bytes = int((artifact.metadata or {}).get("size_bytes", 0) or 0)
        if (
            artifact.kind in {"image", "audio", "video"}
            and artifact.data_url
            and (size_bytes <= ConversationState._INLINE_REFERENCE_MAX_BYTES or size_bytes == 0)
        ):
            record["data_url"] = artifact.data_url
        return record

    def _serialize_turn_records_for_save(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        serialized: list[dict[str, Any]] = []
        inline_turns_remaining = self._INLINE_REFERENCE_TURNS

        for record in reversed(records):
            copied = self._compact_turn_record(record)
            artifacts: list[dict[str, Any]] = []
            artifact_items = [dict(item) for item in record.get("artifacts", [])]
            keep_inline_for_turn = inline_turns_remaining > 0 and any(
                item.get("kind") in {"image", "audio", "video"} and item.get("data_url") for item in artifact_items
            )
            if keep_inline_for_turn:
                inline_turns_remaining -= 1

            for item in artifact_items:
                if not (keep_inline_for_turn and item.get("kind") in {"image", "audio", "video"}):
                    item.pop("data_url", None)
                artifacts.append(item)
            copied["artifacts"] = artifacts
            serialized.append(copied)

        serialized.reverse()
        return serialized

    @staticmethod
    def _record_to_artifact(item: dict[str, Any]) -> MediaArtifact | None:
        kind = str(item.get("kind", "") or "").strip()
        mime_type = str(item.get("mime_type", "") or "").strip()
        name = str(item.get("name", "") or "").strip()
        data_url = str(item.get("data_url", "") or "").strip()
        if kind not in {"image", "audio", "video"} or not data_url:
            return None
        return MediaArtifact(
            kind=kind,
            name=name or kind,
            mime_type=mime_type or {
                "image": "image/png",
                "audio": "audio/wav",
                "video": "video/mp4",
            }.get(kind, "application/octet-stream"),
            summary=str(item.get("summary", "") or ""),
            data_url=data_url,
            uri=item.get("uri"),
            metadata=dict(item.get("metadata") or {}),
        )
