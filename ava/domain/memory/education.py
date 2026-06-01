"""教育场景连续性记忆。"""

from __future__ import annotations

from typing import Any


class EducationMemory:
    """管理教育域的连续性状态。

    该状态只保存结构化原始信息，不负责文本摘要、展示文案或 UI 标签生成。
    """

    def __init__(self) -> None:
        """初始化教育记忆状态。"""
        self._state = self.empty_state()

    @staticmethod
    def empty_state() -> dict[str, Any]:
        """返回空的教育记忆状态。"""
        return {
            "subject": "",
            "knowledge_point": "",
            "stage": "",
            "last_problem": {},
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
        """返回当前状态副本。"""
        return dict(self._state)

    def set_value(self, key: str, value: Any) -> None:
        """按键写入状态值。

        参数:
        - key: 状态键名。
        - value: 要写入的值。
        """
        normalized_key = str(key or "").strip()
        if not normalized_key:
            return
        self._state[normalized_key] = value

    def reset(self) -> None:
        """重置为初始空状态。"""
        self._state = self.empty_state()

    def load_payload(self, payload: dict | None) -> None:
        """从持久化载荷恢复状态。

        参数:
        - payload: 持久化层读取出的教育状态对象。
        """
        state = self.empty_state()
        state.update(dict(payload or {}))
        if not isinstance(state.get("last_problem"), dict):
            state["last_problem"] = {}
        self._state = state

    def to_payload(self) -> dict[str, Any]:
        """导出可持久化的状态载荷。"""
        return dict(self._state)

    def apply_route_transition(self, *, should_preserve_teaching_state: bool) -> None:
        """在路由切换时应用教育状态保留策略。

        参数:
        - should_preserve_teaching_state: 是否保留当前教育连续性状态。
        """
        if not should_preserve_teaching_state:
            self._state = self.empty_state()

    def update_from_strategy(
        self,
        strategy: dict[str, Any] | None,
        *,
        user_message: dict[str, Any] | None = None,
    ) -> None:
        """根据当前轮策略结果更新教育记忆。

        参数:
        - strategy: 当前轮教育策略对象。
        - user_message: 当前轮原始标准用户消息。
        """
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
            self._state["stage"] = "练习" if learning_scenario == "practice" else "讲解"
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
            self._state["last_problem"] = dict(user_message)

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
