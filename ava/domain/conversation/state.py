"""会话状态持久化领域模型。"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from ava.domain.memory import SessionMemory
from ava.domain.memory.message import user_message_summary, user_message_text
from ava.domain.multimodal import MediaArtifact


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

    def __init__(self, state_file: Path | str, memory_size: int = 8, session_id: str = _DEFAULT_SESSION_ID) -> None:
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
                "artifact_continuity": continuity.get("artifact_continuity", ""),
                "carry_reference_artifacts": bool(continuity.get("carry_reference_artifacts", False)),
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
    def _assistant_text_from_message(cls, assistant_message: dict[str, Any] | None) -> str:
        """从标准助手消息中提取文本。"""
        parts: list[str] = []
        for block in list((assistant_message or {}).get("content") or []):
            if not isinstance(block, dict):
                continue
            if str(block.get("type", "") or "").strip() != "output_text":
                continue
            text = str(block.get("text", "") or "").strip()
            if text:
                parts.append(text)
        return "\n".join(parts).strip()

    @classmethod
    def _artifact_records_from_turn_record(cls, record: dict[str, Any]) -> list[dict[str, Any]]:
        """从 turn record 中提取正式附件记录。"""
        user_message = cls.normalize_user_message(record.get("user_message") or {})
        return cls._artifacts_from_user_message(user_message)

    @classmethod
    def _record_with_derived_fields(cls, record: dict[str, Any]) -> dict[str, Any]:
        """把 turn record 归一化到正式消息结构。"""
        copied = dict(record)

        user_message = cls.normalize_user_message(copied.get("user_message") or {})
        assistant_message = cls.normalize_assistant_message(copied.get("assistant_message") or {})

        if not user_message.get("content"):
            artifacts = list(copied.get("artifact_records") or copied.get("artifacts") or [])
            user_text = str(copied.get("user_text", "") or "").strip()
            content: list[dict[str, Any]] = []
            if user_text:
                content.append({"type": "input_text", "text": user_text})
            for item in artifacts:
                if not isinstance(item, dict):
                    continue
                kind = str(item.get("kind", "") or "").strip()
                if kind == "image":
                    image_url = str(item.get("data_url") or item.get("uri") or "").strip()
                    if image_url:
                        content.append({"type": "input_image", "image_url": image_url})
                elif kind == "audio":
                    data_url = str(item.get("data_url", "") or "").strip()
                    fmt = str((item.get("metadata") or {}).get("format", "") or "").strip()
                    if data_url:
                        content.append(
                            {
                                "type": "input_audio",
                                "input_audio": {"data": data_url, "format": fmt or "wav"},
                            }
                        )
                else:
                    block: dict[str, Any] = {"type": "input_file"}
                    name = str(item.get("name", "") or "").strip()
                    uri = str(item.get("uri", "") or "").strip()
                    data_url = str(item.get("data_url", "") or "").strip()
                    if name:
                        block["filename"] = name
                    if uri:
                        block["file_url"] = uri
                    if data_url:
                        block["file_data"] = data_url
                    if len(block) > 1:
                        content.append(block)
            user_message = {"role": "user", "content": content}

        if assistant_message.get("content"):
            pass
        else:
            assistant_text = str(copied.get("assistant_text", "") or "").strip()
            if assistant_text:
                assistant_message = {"role": "assistant", "content": [{"type": "output_text", "text": assistant_text}]}

        copied["user_message"] = user_message
        copied["assistant_message"] = assistant_message
        copied["turn_status"] = str(copied.get("turn_status", "completed") or "completed")
        copied["strategy"] = cls._compact_strategy_payload(dict(copied.get("strategy") or {}))
        copied["evaluation"] = cls._compact_evaluation_payload(dict(copied.get("evaluation") or {}))
        copied["decision"] = dict(copied.get("decision") or {})
        copied.pop("artifact_records", None)
        for legacy_key in ("user_text", "multimodal_summary", "artifacts", "assistant_text"):
            copied.pop(legacy_key, None)
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

    @staticmethod
    def _message_text_from_user_message(user_message: dict[str, Any]) -> str:
        """提取标准用户消息中的纯文本内容。"""
        return user_message_text(user_message)

    @staticmethod
    def _artifacts_from_user_message(user_message: dict[str, Any]) -> list[dict[str, Any]]:
        """把标准用户消息中的非文本块提取为附件缓存结构。"""
        artifacts: list[dict[str, Any]] = []
        for index, block in enumerate(list(user_message.get("content") or []), start=1):
            if not isinstance(block, dict):
                continue
            block_type = str(block.get("type", "") or "").strip()
            if block_type == "input_text":
                continue
            if block_type == "input_image":
                image_url = str(block.get("image_url", "") or "").strip()
                if image_url:
                    artifacts.append(
                        {
                            "kind": "image",
                            "name": f"image-{index}",
                            "mime_type": "image/*",
                            "summary": "",
                            "uri": image_url if not image_url.startswith("data:") else None,
                            "data_url": image_url if image_url.startswith("data:") else None,
                            "metadata": {},
                        }
                    )
                continue
            if block_type == "input_audio":
                payload = dict(block.get("input_audio") or {})
                audio_data = str(payload.get("data", "") or "").strip()
                audio_format = str(payload.get("format", "") or "").strip()
                if audio_data:
                    artifacts.append(
                        {
                            "kind": "audio",
                            "name": f"audio-{index}",
                            "mime_type": f"audio/{audio_format or 'wav'}",
                            "summary": "",
                            "uri": None,
                            "data_url": audio_data,
                            "metadata": {"format": audio_format},
                        }
                    )
                continue
            if block_type == "input_file":
                artifact: dict[str, Any] = {
                    "kind": "file",
                    "name": str(block.get("filename", "") or f"file-{index}").strip(),
                    "mime_type": "",
                    "summary": "",
                    "uri": None,
                    "metadata": {},
                }
                file_url = str(block.get("file_url", "") or "").strip()
                file_data = str(block.get("file_data", "") or "").strip()
                if file_url:
                    artifact["uri"] = file_url
                if file_data:
                    artifact["data_url"] = file_data
                artifacts.append(artifact)
        return artifacts

    @classmethod
    def user_message_summary(cls, user_message: dict[str, Any]) -> str:
        """生成标准用户消息摘要。"""
        return user_message_summary(user_message)

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

    def post_turn(self, user_text: str, assistant_text: str, intent: str) -> None:
        """Append turn content and refresh derived summary fields."""
        user_message = self.normalize_user_message(
            {
                "role": "user",
                "content": [{"type": "input_text", "text": str(user_text or "").strip()}]
                if str(user_text or "").strip()
                else [],
            }
        )
        assistant_message = self.normalize_assistant_message(
            {
                "role": "assistant",
                "content": [{"type": "output_text", "text": str(assistant_text or "").strip()}]
                if str(assistant_text or "").strip()
                else [],
            }
        )
        self.turn_count += 1
        self.intent_counter[intent] = self.intent_counter.get(intent, 0) + 1
        self.memory.append_recent_topic(user_message_text(user_message) or user_message_summary(user_message))
        self.turn_records.append(
            {
                "role": "turn",
                "source": "legacy_text",
                "user_message": user_message,
                "assistant_message": assistant_message,
                "intent": intent,
                "decision": {},
                "strategy": {},
                "evaluation": {},
                "turn_status": "completed",
                "created_at": datetime.now().isoformat(timespec="seconds"),
            }
        )
        self._refresh_summaries()

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
        user_history_text = self.user_message_summary(normalized_user_message) or self._message_text_from_user_message(normalized_user_message)
        record = next((item for item in reversed(self.turn_records) if item.get("turn_id") == turn_id), None)
        if record is None:
            self.turn_count += 1
            self.memory.append_recent_topic(user_history_text)
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
        assistant_text: str,
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
        assistant_message = self.normalize_assistant_message(
            {"role": "assistant", "content": [{"type": "output_text", "text": assistant_text}]}
            if str(assistant_text or "").strip()
            else {"role": "assistant", "content": []}
        )
        record = next((item for item in reversed(self.turn_records) if item.get("turn_id") == turn_id), None)
        if record is None:
            self.turn_count += 1
            self.intent_counter[intent] = self.intent_counter.get(intent, 0) + 1
            self.memory.append_recent_topic(
                self.user_message_summary(normalized_user_message)
                or self._message_text_from_user_message(normalized_user_message)
            )
            self.turn_records.append(
                {
                    "role": "turn",
                    "source": "runtime",
                    "user_message": normalized_user_message,
                    "assistant_message": assistant_message,
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
        record["assistant_message"] = assistant_message
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

        if assistant_text.strip() and turn_status == "completed":
            self.update_responder_conversation_state(
                conversation_id=(llm_response_state or {}).get("conversation_id"),
                previous_response_id=(llm_response_state or {}).get("response_id"),
            )

        self._refresh_summaries()
        if persist:
            self.save()

    def _summarize_turn_records(self, turn_records: list[dict[str, Any]]) -> str:
        if not turn_records:
            return "无"

        lines: list[str] = []
        for record in turn_records:
            turn_status = str(record.get("turn_status", "completed") or "completed").strip()
            user_message = self.normalize_user_message(record.get("user_message") or {})
            assistant_message = self.normalize_assistant_message(record.get("assistant_message") or {})
            user_text = user_message_text(user_message).strip()
            multimodal_summary = user_message_summary(user_message).strip()
            assistant_text = (
                self._assistant_text_from_message(assistant_message).strip()
                if turn_status == "completed"
                else ""
            )
            label = user_text or multimodal_summary or "无"
            artifacts = self._artifacts_from_user_message(user_message)
            if artifacts:
                artifact_labels = []
                for artifact in artifacts:
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
            raw_artifacts = self._artifact_records_from_turn_record(record)
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
            artifact_items = [dict(item) for item in self._artifact_records_from_turn_record(record)]
            keep_inline_for_turn = inline_turns_remaining > 0 and any(
                item.get("kind") in {"image", "audio", "video"} and item.get("data_url") for item in artifact_items
            )
            if keep_inline_for_turn:
                inline_turns_remaining -= 1

            for item in artifact_items:
                if not (keep_inline_for_turn and item.get("kind") in {"image", "audio", "video"}):
                    item.pop("data_url", None)
                artifacts.append(item)
            if artifacts:
                copied["artifact_records"] = artifacts
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
