"""Class-managed context compiler for router and responder phases.

This module is the single source of truth for model-visible context assembly.
Legacy modules may keep thin compatibility wrappers, but the actual logic for:
- snapshot construction
- memory projection
- runtime payload compilation
- router/responder message assembly
belongs here.
"""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

from ava.capabilities.prompt.prompt_builder import (
    PromptCenter,
    build_router_user_message,
)
from ava.context_engine.continuity import (
    build_artifact_brief_for_context,
    should_inherit_reference_artifacts,
)
from ava.context_engine.input import AttachmentPayload, build_turn_input
from ava.context_engine.instructions import InstructionsCompiler
from ava.context_engine.memory import build_memory_projection, retrieve_relevant_memories
from ava.context_engine.types import (
    CompiledContextEnvelope,
    ContextSnapshot,
    SnapshotCompileOptions,
)
from ava.domain.conversation.state import ConversationState
from ava.domain.conversation.strategy import BranchStrategy
from ava.domain.multimodal import TurnInput
from ava.domain.routing.schema import RouteDecision

_REFERENCE_FOLLOWUP_PROMPT = (
    "请继续结合我之前上传的参考材料回答当前问题，"
    "除非当前问题已经明确切换到新的对象。"
)
_REFERENCE_BRIEF_ONLY_PROMPT = (
    "请直接基于之前参考材料的结构化理解和最近对话继续回答，"
    "不要要求我重新上传同一份材料。"
)


class ContextSnapshotBuilder:
    """Build canonical context snapshots for all runtime phases."""

    @staticmethod
    def _artifact_labels(raw_artifacts: list[dict[str, object]]) -> list[str]:
        labels: list[str] = []
        for artifact in raw_artifacts:
            kind = str(artifact.get("kind", "file") or "file").strip()
            name = str(artifact.get("name", "") or "").strip()
            summary = str(artifact.get("summary", "") or "").strip()
            base = f"[{kind}] {name}".strip()
            if summary and summary != name:
                labels.append(f"{base}: {summary}" if base else summary)
            elif base:
                labels.append(base)
        return labels

    @classmethod
    def _record_to_history_messages(cls, record: dict[str, object]) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        user_text = str(record.get("user_text", "") or "").strip()
        multimodal_summary = str(record.get("multimodal_summary", "") or "").strip()
        artifact_lines = cls._artifact_labels(list(record.get("artifacts") or []))

        if user_text and artifact_lines:
            user_content = f"{user_text}\n参考附件：\n" + "\n".join(
                f"- {label}" for label in artifact_lines
            )
        elif user_text:
            user_content = user_text
        elif artifact_lines:
            user_content = "参考附件：\n" + "\n".join(f"- {label}" for label in artifact_lines)
        else:
            user_content = multimodal_summary

        if user_content:
            messages.append({"role": "user", "content": user_content})

        turn_status = str(record.get("turn_status", "completed") or "completed").strip()
        assistant_text = (
            str(record.get("assistant_text", "") or "").strip()
            if turn_status == "completed"
            else ""
        )
        if assistant_text:
            messages.append({"role": "assistant", "content": assistant_text})
        return messages

    def build(
        self,
        *,
        state: ConversationState,
        turn_input: TurnInput | str,
        options: SnapshotCompileOptions,
    ) -> ContextSnapshot:
        """Build the canonical context snapshot for one phase."""

        if isinstance(turn_input, str):
            turn_input = build_turn_input(turn_input)

        max_messages = max(2, int(options.max_context_messages or (options.history_window * 2)))
        if options.current_turn_id is None:
            turn_records = state.turn_records[-max_messages:]
        else:
            turn_records = [
                item
                for item in state.turn_records
                if item.get("turn_id") != options.current_turn_id
            ][-max_messages:]

        flattened_history: list[dict[str, str]] = []
        for record in turn_records:
            flattened_history.extend(self._record_to_history_messages(record))
        sanitized_history = flattened_history[-max_messages:]

        user_text = turn_input.normalized_text() or turn_input.multimodal_summary()
        allow_reference_artifacts = (
            should_inherit_reference_artifacts(state, turn_input)
            if options.include_reference_artifacts is None
            else bool(options.include_reference_artifacts)
        )

        reference_artifacts = ()
        if allow_reference_artifacts and not turn_input.artifacts:
            reference_artifacts = state.recent_reference_artifacts(
                current_turn_id=options.current_turn_id,
                limit_turns=1,
            )

        artifact_brief = build_artifact_brief_for_context(
            state,
            current_artifacts=turn_input.artifacts,
            reference_artifacts=reference_artifacts,
        )
        memory_projection = build_memory_projection(
            state,
            profile=options.profile,
            turn_input=turn_input,
            current_artifacts=turn_input.artifacts,
            reference_artifacts=reference_artifacts,
        )
        retrieved_memories = retrieve_relevant_memories(
            state,
            turn_input,
            current_artifacts=turn_input.artifacts,
            reference_artifacts=reference_artifacts,
        )

        return ContextSnapshot(
            turn_input=turn_input,
            user_text=user_text,
            session_id=state.session_id,
            session_scene=state.session_scene,
            turn_scene=state.turn_scene,
            history_messages=sanitized_history,
            artifacts=turn_input.artifacts,
            reference_artifacts=reference_artifacts,
            turn_records=turn_records,
            context_profile=options.profile,
            reference_artifacts_inherited=bool(reference_artifacts),
            router_artifact_brief=artifact_brief,
            router_plan={},
            memory_projection=memory_projection,
            retrieved_memories=retrieved_memories,
        )


class RuntimePayloadCompiler:
    """Compile model-visible runtime payloads from snapshots."""

    @staticmethod
    def _compact_dict(
        value: dict[str, Any],
        *,
        allowed_keys: tuple[str, ...] | None = None,
    ) -> dict[str, Any]:
        source = dict(value or {})
        if allowed_keys is not None:
            source = {key: source.get(key) for key in allowed_keys if key in source}
        return {
            str(key): item
            for key, item in source.items()
            if item not in (None, "", [], {}, ())
        }

    def _compact_turn_records(
        self,
        snapshot: ContextSnapshot,
        *,
        limit: int = 3,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for record in list(getattr(snapshot, "turn_records", []) or [])[-limit:]:
            decision = self._compact_dict(dict(record.get("decision") or {}))
            strategy = dict(record.get("strategy") or {})
            analysis = dict(strategy.get("analysis") or {})
            frame = dict(analysis.get("education_turn_frame") or analysis.get("task_frame") or {})
            items.append(
                {
                    "user_text": str(record.get("user_text", "") or "").strip(),
                    "assistant_text": str(record.get("assistant_text", "") or "").strip(),
                    "decision": decision,
                    "strategy_id": str(strategy.get("strategy_id", "") or "").strip(),
                    "policy_id": str(strategy.get("policy_id", "") or "").strip(),
                    "frame": self._compact_dict(
                        frame,
                        allowed_keys=(
                            "primary_scenario",
                            "primary_action",
                            "learning_objects",
                            "object_scope",
                            "object_continuity",
                        ),
                    ),
                }
            )
        return items

    def _base_runtime_context(self, snapshot: ContextSnapshot, *, phase: str) -> dict[str, Any]:
        return {
            "schema_version": "runtime_context.v2",
            "phase": phase,
            "session": {
                "session_id": snapshot.session_id,
                "session_scene": snapshot.session_scene,
                "turn_scene": snapshot.turn_scene,
                "context_profile": snapshot.context_profile,
            },
            "input": {
                "user_text": snapshot.user_text,
                "artifacts_count": len(snapshot.artifacts),
                "reference_artifacts_count": len(snapshot.reference_artifacts),
                "reference_artifacts_inherited": bool(snapshot.reference_artifacts_inherited),
            },
            "context": {
                "history_messages_count": len(snapshot.history_messages),
                "recent_turn_records": self._compact_turn_records(snapshot),
            },
            "memory": self._compact_dict(dict(snapshot.memory_projection or {})),
        }

    def compile_router(self, snapshot: ContextSnapshot) -> dict[str, Any]:
        payload = self._base_runtime_context(snapshot, phase="router")
        payload["router"] = {
            "must_return_valid_json": True,
            "must_return_plan": True,
            "instructions": {
                "infer_intent_from_current_input_and_recent_history": True,
                "detect_followup_vs_topic_switch": True,
                "do_not_ignore_history_when_user_text_is_short": True,
                "education_plan_must_include": [
                    "module",
                    "subject",
                    "style",
                    "policy_id",
                    "primary_scenario",
                    "primary_action",
                    "learning_objects",
                    "object_scope",
                    "object_continuity",
                    "answer_boundary",
                ],
                "non_education_plan_must_include": ["mode"],
            },
            "output_schema": {
                "session_scene": "education|general",
                "turn_scene": "education|general_qa|casual_chat|clarify",
                "intent": "string",
                "confidence": 0.0,
                "should_preserve_teaching_state": True,
                "need_clarification": False,
                "plan": {
                    "branch": "education|general_qa|casual_chat|clarify",
                    "mode": (
                        "fact|reasoned|howto|compare|troubleshoot|visual|confirm|reaction|"
                        "praise|backchannel|companion|humor|smalltalk|missing_material|"
                        "focus|missing_reference|answer_mode|scene|subject"
                    ),
                    "module": "solve|check|explain|drill|answer|qa",
                    "subject": "math|english|chinese|cs|physics|history|general",
                    "style": "direct|explain_careful|hint_only|step_by_step",
                    "policy_id": "string",
                    "primary_scenario": "practice|lesson|concept|qa|general",
                    "primary_action": "string",
                    "learning_objects": ["string"],
                    "object_scope": "string",
                    "object_continuity": "same|new|uncertain",
                    "answer_boundary": (
                        "hint_first|full_solution|direct_explain|contextual_only|targeted_answer"
                    ),
                    "prompt_overrides": ["string"],
                    "plan_reason": "string",
                },
            },
            "router_artifact_brief": self._compact_dict(dict(snapshot.router_artifact_brief or {})),
        }
        return payload

    def compile_responder(
        self,
        snapshot: ContextSnapshot,
        strategy: BranchStrategy,
        decision: RouteDecision | None = None,
    ) -> dict[str, Any]:
        payload = self._base_runtime_context(snapshot, phase="responder")
        analysis = dict(getattr(strategy, "analysis", {}) or {})
        frame = dict(analysis.get("education_turn_frame") or analysis.get("task_frame") or {})
        payload["decision"] = decision.model_dump() if decision is not None else {}
        payload["strategy"] = {
            "branch": strategy.branch,
            "strategy_id": strategy.strategy_id,
            "delivery_mode": strategy.delivery_mode,
            "ui_mode": strategy.ui_mode,
            "policy_id": strategy.policy_id,
            "mode": strategy.mode,
            "module": strategy.module,
            "scene": strategy.scene,
            "subject": strategy.subject,
            "style": strategy.style,
            "source": strategy.source,
            "response_contract": dict(strategy.response_contract or {}),
            "speech_policy": dict(strategy.speech_policy or {}),
        }
        payload["teaching"] = {
            "analysis": self._compact_dict(
                analysis,
                allowed_keys=(
                    "subject",
                    "primary_scenario",
                    "primary_action",
                    "learning_objects",
                    "object_scope",
                    "object_continuity",
                    "answer_boundary",
                    "selected_strategy_id",
                    "selected_policy_id",
                    "selected_strategy_source",
                ),
            ),
            "frame": self._compact_dict(frame),
            "router_plan": self._compact_dict(dict(snapshot.router_plan or {})),
            "router_artifact_brief": self._compact_dict(dict(snapshot.router_artifact_brief or {})),
        }
        return payload

    def build_runtime_context_message(self, payload: dict[str, Any]) -> dict[str, str]:
        return {
            "role": "system",
            "content": "Runtime context (JSON, internal only):\n" + json.dumps(payload, ensure_ascii=False),
        }


class MessageCompiler:
    """Compile router and responder messages from canonical snapshots."""

    @staticmethod
    def _should_include_history_messages(strategy: BranchStrategy) -> bool:
        analysis = dict(getattr(strategy, "analysis", {}) or {})
        context_policy = dict(analysis.get("prompt_context_policy", {}) or {})
        return bool(context_policy.get("include_history_messages", True))

    @staticmethod
    def _should_attach_reference_artifacts(
        snapshot: ContextSnapshot,
        strategy: BranchStrategy,
    ) -> bool:
        if snapshot.artifacts or not snapshot.reference_artifacts:
            return False

        artifact_brief = dict(getattr(snapshot, "router_artifact_brief", {}) or {})
        if artifact_brief:
            return bool(artifact_brief.get("followup_requires_visual_reread", False))

        analysis = dict(getattr(strategy, "analysis", {}) or {})
        continuity = dict(analysis.get("continuity", {}) or {})
        education_turn_frame = dict(analysis.get("education_turn_frame", {}) or {})
        scenario_policy = dict(education_turn_frame.get("scenario_policy", {}) or {})
        learning_objects = {
            str(item).strip()
            for item in (education_turn_frame.get("learning_objects") or [])
            if str(item).strip()
        }
        return bool(
            continuity.get("carry_reference_artifacts")
            or scenario_policy.get("answer_boundary") == "contextual_only"
            or "lesson_segment" in learning_objects
        )

    def compile_router(
        self,
        *,
        instructions_text: str,
        snapshot: ContextSnapshot,
        text_only: bool = False,
    ) -> list[dict[str, object]]:
        messages: list[dict[str, object]] = [{"role": "system", "content": instructions_text}]
        if snapshot.history_messages:
            messages.extend(snapshot.history_messages)
        messages.append(build_router_user_message(snapshot, text_only=text_only))
        return messages

    def compile_responder(
        self,
        *,
        instructions_text: str,
        snapshot: ContextSnapshot,
        strategy: BranchStrategy,
        decision: RouteDecision | None = None,
    ) -> list[dict[str, object]]:
        del decision
        user_content: list[dict[str, object]] = []
        text = snapshot.turn_input.normalized_text()
        if text:
            user_content.append({"type": "text", "text": text})

        for artifact in snapshot.artifacts:
            block = artifact.to_message_block()
            if block:
                user_content.append(block)

        if self._should_attach_reference_artifacts(snapshot, strategy):
            user_content.append({"type": "text", "text": _REFERENCE_FOLLOWUP_PROMPT})
            for artifact in snapshot.reference_artifacts:
                block = artifact.to_message_block()
                if block:
                    user_content.append(block)
        elif snapshot.reference_artifacts and snapshot.router_artifact_brief:
            user_content.append({"type": "text", "text": _REFERENCE_BRIEF_ONLY_PROMPT})

        if not user_content:
            user_content.append({"type": "text", "text": snapshot.user_text})

        messages: list[dict[str, object]] = [{"role": "system", "content": instructions_text}]
        if self._should_include_history_messages(strategy) and snapshot.history_messages:
            messages.extend(snapshot.history_messages)
        content: object
        if len(user_content) == 1 and user_content[0].get("type") == "text":
            content = user_content[0]["text"]
        else:
            content = user_content
        messages.append({"role": "user", "content": content})
        return messages


class ContextCompiler:
    """Unified class-managed context compiler."""

    def __init__(
        self,
        *,
        snapshot_builder: ContextSnapshotBuilder | None = None,
        runtime_compiler: RuntimePayloadCompiler | None = None,
        message_compiler: MessageCompiler | None = None,
        instructions_compiler: InstructionsCompiler | None = None,
    ) -> None:
        self.snapshot_builder = snapshot_builder or ContextSnapshotBuilder()
        self.runtime_compiler = runtime_compiler or RuntimePayloadCompiler()
        self.message_compiler = message_compiler or MessageCompiler()
        self.instructions_compiler = instructions_compiler or InstructionsCompiler()

    def build_turn_input(
        self,
        text: str | None = None,
        attachments: list[AttachmentPayload] | None = None,
        source: str = "web",
    ) -> TurnInput:
        return build_turn_input(text=text, attachments=attachments, source=source)

    def build_snapshot(
        self,
        *,
        state: ConversationState,
        turn_input: TurnInput | str,
        options: SnapshotCompileOptions,
    ) -> ContextSnapshot:
        return self.snapshot_builder.build(state=state, turn_input=turn_input, options=options)

    def compile_router_envelope(
        self,
        *,
        prompt_center: PromptCenter,
        state: ConversationState,
        turn_input: TurnInput | str,
        options: SnapshotCompileOptions,
        snapshot: ContextSnapshot | None = None,
        text_only: bool = False,
    ) -> CompiledContextEnvelope:
        current_snapshot = snapshot or self.build_snapshot(
            state=state,
            turn_input=turn_input,
            options=options,
        )
        runtime_context = self.runtime_compiler.compile_router(current_snapshot)
        compiled_instructions = self.instructions_compiler.compile_router(
            prompt_center=prompt_center,
            snapshot=current_snapshot,
            runtime_context=runtime_context,
        )
        messages = self.message_compiler.compile_router(
            instructions_text=compiled_instructions.text,
            snapshot=current_snapshot,
            text_only=text_only,
        )
        return CompiledContextEnvelope(
            phase="router",
            snapshot=current_snapshot,
            instructions=compiled_instructions.text,
            runtime_context=runtime_context,
            messages=messages,
            active_skills=list(compiled_instructions.active_skills),
            metadata={
                "text_only": text_only,
                "context_profile": current_snapshot.context_profile,
                "instruction_sections": compiled_instructions.sections,
            },
        )

    def compile_responder_envelope(
        self,
        *,
        prompt_center: PromptCenter,
        state: ConversationState,
        turn_input: TurnInput | str,
        strategy: BranchStrategy,
        decision: RouteDecision | None,
        options: SnapshotCompileOptions,
        snapshot: ContextSnapshot | None = None,
        previous_snapshot: ContextSnapshot | None = None,
    ) -> CompiledContextEnvelope:
        current_snapshot = snapshot or self.build_snapshot(
            state=state,
            turn_input=turn_input,
            options=options,
        )
        if previous_snapshot is not None:
            current_snapshot = replace(
                current_snapshot,
                router_artifact_brief=dict(getattr(previous_snapshot, "router_artifact_brief", {}) or {}),
                router_plan=dict(getattr(previous_snapshot, "router_plan", {}) or {}),
            )
        runtime_context = self.runtime_compiler.compile_responder(
            current_snapshot,
            strategy,
            decision,
        )
        compiled_instructions = self.instructions_compiler.compile_responder(
            prompt_center=prompt_center,
            snapshot=current_snapshot,
            strategy=strategy,
            decision=decision,
            runtime_context=runtime_context,
        )
        messages = self.message_compiler.compile_responder(
            instructions_text=compiled_instructions.text,
            snapshot=current_snapshot,
            strategy=strategy,
            decision=decision,
        )
        return CompiledContextEnvelope(
            phase="responder",
            snapshot=current_snapshot,
            instructions=compiled_instructions.text,
            runtime_context=runtime_context,
            messages=messages,
            active_skills=list(compiled_instructions.active_skills),
            metadata={
                "context_profile": current_snapshot.context_profile,
                "strategy_id": strategy.strategy_id,
                "instruction_sections": compiled_instructions.sections,
            },
        )
