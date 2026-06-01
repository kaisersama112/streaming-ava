"""会话状态持久化领域模型。"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from ava.domain.memory import SessionMemory


class ConversationState:
    """可持久化的会话聚合根。

    当前版本的正式存储结构以标准消息为核心：
    - `user_message`
    - `assistant_message`
    """

    _DEFAULT_SESSION_ID = "default"
    _SESSION_CONTAINER_KEY = "sessions"
    _INLINE_REFERENCE_TURNS = 2
    _INLINE_REFERENCE_MAX_BYTES = 1_500_000

    def __init__(
            self,
            state_file: Path | str,
            memory_size: int = 8,
            session_id: str = _DEFAULT_SESSION_ID
    ) -> None:
        self.state_file = Path(state_file)
        self.memory_size = memory_size
        self.session_id = self.normalize_session_id(session_id)
        self.memory = SessionMemory(memory_size=memory_size)
        self.intent_counter: dict[str, int] = {}
        self.turn_count: int = 0
        self.turn_records: list[dict[str, Any]] = []
        self.session_scene: str = "general"
        self.turn_scene: str = "general_qa"
        self.responder_conversation_id: str = ""
        self.responder_previous_response_id: str = ""

    @classmethod
    def normalize_session_id(cls, session_id: str | None) -> str:
        normalized = str(session_id or "").strip()
        if not normalized:
            return cls._DEFAULT_SESSION_ID
        normalized = re.sub(r"[^\w\-.:]", "_", normalized)
        return normalized[:64] or cls._DEFAULT_SESSION_ID

    def _reset_fields(self) -> None:
        self.memory.reset()
        self.intent_counter = {}
        self.turn_count = 0
        self.turn_records = []
        self.session_scene = "general"
        self.turn_scene = "general_qa"
        self.responder_conversation_id = ""
        self.responder_previous_response_id = ""

    def _session_payload(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "intent_counter": self.intent_counter,
            "turn_count": self.turn_count,
            "turn_records": self._serialize_turn_records_for_save(self.turn_records[-40:]),
            "session_scene": self.session_scene,
            "turn_scene": self.turn_scene,
            "llm_state": {
                "responder_conversation_id": self.responder_conversation_id,
                "responder_previous_response_id": self.responder_previous_response_id,
            },
            "memory": self.memory.to_payload(
                turn_records=self.turn_records,
            ),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }

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
                "message_block_subject_hint",
                "message_block_task_hint",
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
                "pedagogy_change_only": bool(
                    frame.get("pedagogy_change_only", frame.get("style_change_only", False))
                ),
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
                "message_block_continuity": continuity.get("message_block_continuity", ""),
                "carry_reference_message_blocks": bool(
                    continuity.get("carry_reference_message_blocks", False)
                ),
                "allow_fast_path": bool(continuity.get("allow_fast_path", False)),
                "user_requests_pedagogy_change_only": bool(
                    continuity.get(
                        "user_requests_pedagogy_change_only",
                        continuity.get("user_requests_style_change_only", False),
                    )
                ),
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
            "pedagogy": str(strategy.get("pedagogy") or strategy.get("style") or "").strip(),
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
                "pedagogy",
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

    @staticmethod
    def _normalize_user_message_blocks(content: Any) -> list[dict[str, Any]]:
        """规范化用户消息内容块。"""
        normalized: list[dict[str, Any]] = []
        for block in list(content or []):
            if not isinstance(block, dict):
                continue
            block_type = str(block.get("type", "") or "").strip()
            if block_type == "input_text":
                text = str(block.get("text", "") or "").strip()
                if text:
                    normalized.append({"type": "input_text", "text": text})
                continue
            if block_type == "input_image":
                image_url = str(block.get("image_url", "") or "").strip()
                if image_url:
                    normalized.append({"type": "input_image", "image_url": image_url})
                continue
            if block_type == "input_audio":
                payload = dict(block.get("input_audio") or {})
                audio_data = str(payload.get("data", "") or "").strip()
                audio_format = str(payload.get("format", "") or "").strip()
                if audio_data:
                    normalized.append(
                        {
                            "type": "input_audio",
                            "input_audio": {
                                "data": audio_data,
                                "format": audio_format or "wav",
                            },
                        }
                    )
                continue
            if block_type == "input_file":
                normalized_block: dict[str, Any] = {"type": "input_file"}
                for key in ("file_id", "file_data", "file_url", "filename"):
                    value = block.get(key)
                    if value not in (None, ""):
                        normalized_block[key] = value
                if len(normalized_block) > 1:
                    normalized.append(normalized_block)
        return normalized

    @classmethod
    def normalize_user_message(cls, user_message: dict[str, Any] | None) -> dict[str, Any]:
        """规范化标准用户消息。"""
        payload = dict(user_message or {})
        role = str(payload.get("role", "user") or "user").strip() or "user"
        return {
            "role": role,
            "content": cls._normalize_user_message_blocks(payload.get("content") or []),
        }

    @staticmethod
    def normalize_assistant_message(assistant_message: dict[str, Any] | None) -> dict[str, Any]:
        """规范化标准助手消息。"""
        payload = dict(assistant_message or {})
        content = payload.get("content") or []
        normalized: list[dict[str, Any]] = []
        for block in list(content):
            if not isinstance(block, dict):
                continue
            block_type = str(block.get("type", "") or "").strip()
            if block_type != "output_text":
                continue
            text = str(block.get("text", "") or "").strip()
            if text:
                normalized.append({"type": "output_text", "text": text})
        return {
            "role": "assistant",
            "content": normalized,
        }


    @classmethod
    def _record_with_derived_fields(cls, record: dict[str, Any]) -> dict[str, Any]:
        """把 turn record 归一化到正式消息结构。"""
        copied = dict(record)

        user_message = cls.normalize_user_message(copied.get("user_message") or {})
        assistant_message = cls.normalize_assistant_message(copied.get("assistant_message") or {})

        user_message = cls.normalize_user_message(user_message)
        assistant_message = cls.normalize_assistant_message(assistant_message)

        copied["user_message"] = user_message
        copied["assistant_message"] = assistant_message
        copied["turn_status"] = str(copied.get("turn_status", "completed") or "completed")
        copied["strategy"] = cls._compact_strategy_payload(dict(copied.get("strategy") or {}))
        copied["evaluation"] = cls._compact_evaluation_payload(dict(copied.get("evaluation") or {}))
        copied["decision"] = dict(copied.get("decision") or {})
        return copied

    def _compact_turn_record(self, record: dict[str, Any]) -> dict[str, Any]:
        copied = dict(record)
        copied = self._record_with_derived_fields(copied)
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
        self.intent_counter = data.get("intent_counter", {})
        self.turn_count = data.get("turn_count", 0)
        self.turn_records = self._normalize_loaded_turn_records(data.get("turn_records", []))
        self.session_scene = data.get("session_scene", "general")
        self.turn_scene = data.get("turn_scene", "general_qa")
        llm_state = dict(data.get("llm_state") or {})
        self.responder_conversation_id = str(llm_state.get("responder_conversation_id", "") or "").strip()
        self.responder_previous_response_id = str(llm_state.get("responder_previous_response_id", "") or "").strip()
        self.memory.load_payload(
            data,
            turn_records=self.turn_records,
        )
        self._normalize_loaded_route_state()
        self.memory.refresh_summaries(turn_records=self.turn_records)

    def _last_decision_payload_from_turn_records(self) -> tuple[dict[str, Any], dict[str, Any]]:
        for record in reversed(self.turn_records):
            if str(record.get("turn_status", "completed") or "completed").strip() == "pending":
                continue
            decision = record.get("decision")
            strategy = record.get("strategy")
            if isinstance(decision, dict) and any(
                    str(decision.get(key) or "").strip() for key in ("session_scene", "turn_scene")):
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
            self.memory.update_education_state_from_strategy(strategy)

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
            self.memory.update_education_state_from_strategy(strategy)

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
        self.memory.refresh_summaries(turn_records=self.turn_records)
        self.save()

    def apply_route(
            self,
            session_scene: str,
            turn_scene: str,
            should_preserve_teaching_state: bool = True,
    ) -> None:
        """Update scene state and optionally reset teaching progress."""
        self.session_scene = session_scene
        self.turn_scene = turn_scene
        self.memory.apply_route_transition(should_preserve_teaching_state=should_preserve_teaching_state)

    def responder_conversation_state(self) -> dict[str, str]:
        return {
            "conversation_id": self.responder_conversation_id,
            "previous_response_id": self.responder_previous_response_id,
        }

    def update_responder_conversation_state(
            self,
            *,
            conversation_id: str | None = None,
            previous_response_id: str | None = None,
    ) -> None:
        if conversation_id is not None:
            self.responder_conversation_id = str(conversation_id or "").strip()
        if previous_response_id is not None:
            self.responder_previous_response_id = str(previous_response_id or "").strip()

    def clear_responder_conversation_state(self) -> None:
        self.responder_conversation_id = ""
        self.responder_previous_response_id = ""

    def upsert_realtime_user_turn(
            self,
            turn_id: int,
            user_message: dict[str, Any],
            *,
            source: str = "runtime",
            refresh_summaries: bool = False,
    ) -> None:
        """Persist the user side of a realtime turn before the assistant finishes.

        This keeps follow-up turns context-aware even when the current reply is
        interrupted or still in flight.
        """
        normalized_user_message = self.normalize_user_message(user_message)
        record = next((item for item in reversed(self.turn_records) if item.get("turn_id") == turn_id), None)
        if record is None:
            self.turn_count += 1
            self.turn_records.append(
                {
                    "role": "turn",
                    "turn_id": turn_id,
                    "source": source,
                    "user_message": normalized_user_message,
                    "assistant_message": {"role": "assistant", "content": []},
                    "intent": "",
                    "decision": {},
                    "strategy": {},
                    "evaluation": {},
                    "turn_status": "pending",
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                }
            )
        else:
            record["source"] = source
            record["user_message"] = normalized_user_message
            record["assistant_message"] = self.normalize_assistant_message(record.get("assistant_message") or {})
        if refresh_summaries:
            self._refresh_summaries()

    def complete_realtime_turn(
            self,
            turn_id: int,
            *,
            user_message: dict[str, Any],
            assistant_message: dict[str, Any],
            intent: str,
            decision: dict[str, Any] | None = None,
            strategy: dict[str, Any] | None = None,
            evaluation: dict[str, Any] | None = None,
            turn_status: str = "completed",
            persist: bool = True,
            llm_response_state: dict[str, Any] | None = None,
    ) -> None:
        """Finalize a realtime turn previously inserted by upsert_realtime_user_turn."""
        normalized_user_message = self.normalize_user_message(user_message)
        normalized_assistant_message = self.normalize_assistant_message(assistant_message)
        record = next((item for item in reversed(self.turn_records) if item.get("turn_id") == turn_id), None)
        if record is None:
            self.turn_count += 1
            self.intent_counter[intent] = self.intent_counter.get(intent, 0) + 1
            self.turn_records.append(
                {
                    "role": "turn",
                    "source": "runtime",
                    "user_message": normalized_user_message,
                    "assistant_message": normalized_assistant_message,
                    "intent": intent,
                    "decision": decision or {},
                    "strategy": self._compact_strategy_payload(strategy or {}),
                    "evaluation": self._compact_evaluation_payload(evaluation or {}),
                    "turn_status": turn_status,
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                }
            )
            if persist:
                self._refresh_summaries()
            return

        if intent:
            self.intent_counter[intent] = self.intent_counter.get(intent, 0) + 1

        record["user_message"] = normalized_user_message
        record["assistant_message"] = normalized_assistant_message
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
            self.memory.update_education_state_from_strategy(
                strategy or {},
                user_message=normalized_user_message,
            )

        if normalized_assistant_message.get("content") and turn_status == "completed":
            self.update_responder_conversation_state(
                conversation_id=(llm_response_state or {}).get("conversation_id"),
                previous_response_id=(llm_response_state or {}).get("response_id"),
            )

        self._refresh_summaries()
        if persist:
            self.save()

    def _serialize_turn_records_for_save(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        serialized: list[dict[str, Any]] = []

        for record in reversed(records):
            copied = self._compact_turn_record(record)
            serialized.append(copied)

        serialized.reverse()
        return serialized


