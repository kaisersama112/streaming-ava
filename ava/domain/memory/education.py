"""Education-scene continuity memory."""

from __future__ import annotations

import re
from typing import Any

from .message import user_message_summary


class EducationMemory:
    def __init__(self) -> None:
        self._state = self.empty_state()

    @staticmethod
    def empty_state() -> dict[str, Any]:
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

    @property
    def state(self) -> dict[str, Any]:
        return dict(self._state)

    def set_value(self, key: str, value: Any) -> None:
        normalized_key = str(key or "").strip()
        if not normalized_key:
            return
        self._state[normalized_key] = value

    def reset(self) -> None:
        self._state = self.empty_state()

    def load_payload(self, payload: dict | None) -> None:
        state = self.empty_state()
        state.update(dict(payload or {}))
        self._state = state

    def to_payload(self) -> dict[str, Any]:
        return dict(self._state)

    def apply_route_transition(self, *, should_preserve_teaching_state: bool) -> None:
        if not should_preserve_teaching_state:
            self._state = self.empty_state()

    def update_from_text(self, user_text: str) -> None:
        match_subject = re.search(r"(??|??|??|??|??|??|??|??|??)", user_text)
        if match_subject:
            self._state["subject"] = match_subject.group(1)

        match_point = re.search(
            r"(?:??|??|??|??|??|??|????|??)([\u4e00-\u9fa5A-Za-z0-9_??,??()\-]{2,30})",
            user_text,
        )
        if "???" in user_text and not match_point:
            self._state["knowledge_point"] = user_text[:30]
        elif match_point:
            self._state["knowledge_point"] = match_point.group(1).strip("????")

        if any(keyword in user_text for keyword in ["??", "??", "??", "???"]):
            self._state["stage"] = "??"
        if any(keyword in user_text for keyword in ["??", "??", "??"]):
            self._state["stage"] = "??"
            self._state["last_problem"] = user_text[:40]

    def update_from_strategy(
        self,
        strategy: dict[str, Any] | None,
        *,
        user_message: dict[str, Any] | None = None,
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
            or self._state.get("subject")
            or ""
        ).strip()
        if subject:
            self._state["subject"] = subject

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
        answer_boundary = str(
            scenario_policy.get("answer_boundary") or analysis.get("answer_boundary") or ""
        ).strip()

        if learning_scenario:
            self._state["learning_scenario"] = learning_scenario
            self._state["stage"] = "??" if learning_scenario == "practice" else "??"
        if learning_objects:
            self._state["learning_objects"] = learning_objects
        if object_scope:
            self._state["object_scope"] = object_scope
        if object_continuity:
            self._state["object_continuity"] = object_continuity
        if primary_action:
            self._state["primary_action"] = primary_action
        self._state["secondary_actions"] = secondary_actions
        if answer_boundary:
            self._state["answer_boundary"] = answer_boundary

        knowledge_point = str(analysis.get("knowledge_point") or self._state.get("knowledge_point") or "").strip()
        if knowledge_point:
            self._state["knowledge_point"] = knowledge_point

        if user_message is not None and "problem" in set(learning_objects):
            current_problem = user_message_summary(user_message)
            if current_problem:
                self._state["last_problem"] = current_problem[:80]

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
        self._state["previous_branch"] = branch
        self._state["previous_strategy_id"] = strategy_id
        self._state["previous_policy_id"] = policy_id
        self._state["previous_strategy_state"] = previous_state
