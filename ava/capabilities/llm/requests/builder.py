import json
from typing import Any

from ava.domain.conversation.strategy import BranchStrategy

from ava.capabilities.llm.context.multimodal import (
    artifacts_to_blocks,
    should_attach_reference_artifacts,
)
from ava.capabilities.llm.context.types import InferenceVisibleContext
from ava.capabilities.llm.requests.policy import (
    resolve_model,
    resolve_temperature,
    resolve_timeout,
)
from ava.capabilities.llm.types import InferenceRequest, InferenceTask, LLMContext
from ava.capabilities.prompt.prompt_builder import (
    build_responder_system_prompt,
    build_router_system_prompt,
)
from ava.capabilities.prompt.prompt_loader import PromptCenter


def _compact_dict(value: dict[str, Any], *, allowed_keys: tuple[str, ...] | None = None) -> dict[str, Any]:
    source = dict(value or {})
    if allowed_keys is not None:
        source = {key: source.get(key) for key in allowed_keys if key in source}
    return {
        str(key): item
        for key, item in source.items()
        if item not in (None, "", [], {}, ())
    }


def _compact_turn_records(visible_context: InferenceVisibleContext, limit: int = 3) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for record in list(getattr(visible_context, "turn_records", []) or [])[-limit:]:
        decision = _compact_dict(dict(record.get("decision") or {}))
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
                "frame": _compact_dict(
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


def _build_router_inference_context(context: LLMContext, visible_context: InferenceVisibleContext) -> dict[str, Any]:
    return {
        "schema_version": "inference_context.v1",
        "phase": "router",
        "session": {
            "session_id": visible_context.session_id,
            "session_scene": visible_context.session_scene,
            "turn_scene": visible_context.turn_scene,
            "context_profile": visible_context.context_profile,
        },
        "input": {
            "user_text": visible_context.user_text,
            "artifacts_count": len(visible_context.artifacts),
            "reference_artifacts_count": len(visible_context.reference_artifacts),
            "reference_artifacts_inherited": bool(visible_context.reference_artifacts_inherited),
        },
        "context": {
            "history_messages_count": len(visible_context.history_messages),
            "recent_turn_records": _compact_turn_records(visible_context),
        },
        "router": {
            "must_return_valid_json": True,
            "must_return_plan": True,
            "instructions": {
                "infer_intent_from_current_input_and_recent_history": True,
                "detect_followup_vs_topic_switch": True,
                "do_not_ignore_history_when_user_text_is_short": True,
            },
            "router_artifact_brief": _compact_dict(dict(visible_context.router_artifact_brief or {})),
        },
    }


def _build_responder_inference_context(
    context: LLMContext,
    visible_context: InferenceVisibleContext,
    strategy: BranchStrategy,
) -> dict[str, Any]:
    analysis = dict(getattr(strategy, "analysis", {}) or {})
    frame = dict(analysis.get("education_turn_frame") or analysis.get("task_frame") or {})
    return {
        "schema_version": "inference_context.v1",
        "phase": "responder",
        "session": {
            "session_id": visible_context.session_id,
            "session_scene": visible_context.session_scene,
            "turn_scene": visible_context.turn_scene,
            "context_profile": visible_context.context_profile,
        },
        "input": {
            "user_text": visible_context.user_text,
            "artifacts_count": len(visible_context.artifacts),
            "reference_artifacts_count": len(visible_context.reference_artifacts),
            "reference_artifacts_inherited": bool(visible_context.reference_artifacts_inherited),
        },
        "context": {
            "history_messages_count": len(visible_context.history_messages),
            "recent_turn_records": _compact_turn_records(visible_context),
        },
        "decision": dict(context.routing or {}),
        "strategy": {
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
        },
        "teaching": {
            "analysis": _compact_dict(
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
            "frame": _compact_dict(frame),
            "router_plan": _compact_dict(dict(visible_context.router_plan or {})),
            "router_artifact_brief": _compact_dict(dict(visible_context.router_artifact_brief or {})),
        },
    }


def _router_input(visible_context: InferenceVisibleContext, *, text_only: bool) -> str | list[dict[str, object]]:
    blocks: list[dict[str, object]] = [{"type": "text", "text": visible_context.user_text or "无"}]
    if not text_only:
        blocks.extend(artifacts_to_blocks(visible_context.artifacts))
        if not visible_context.artifacts:
            blocks.extend(artifacts_to_blocks(visible_context.reference_artifacts))
    return blocks


def _generation_input(visible_context: InferenceVisibleContext, strategy: BranchStrategy) -> str | list[dict[str, object]]:
    user_content: list[dict[str, object]] = []
    text = visible_context.turn_input.normalized_text()
    if text:
        user_content.append({"type": "text", "text": text})

    user_content.extend(artifacts_to_blocks(visible_context.artifacts))

    if should_attach_reference_artifacts(visible_context, strategy):
        user_content.append(
            {
                "type": "text",
                "text": "请继续结合我之前上传的参考图片来回答当前问题，除非当前问题明确切换了对象。",
            }
        )
        user_content.extend(artifacts_to_blocks(visible_context.reference_artifacts))
    elif visible_context.reference_artifacts and visible_context.router_artifact_brief:
        user_content.append(
            {
                "type": "text",
                "text": "请直接基于之前题图的结构化理解和最近对话继续回答，不要要求我重新上传同一张图片。",
            }
        )

    if not user_content:
        user_content.append({"type": "text", "text": visible_context.user_text})

    if len(user_content) == 1 and user_content[0].get("type") == "text":
        return str(user_content[0].get("text", "") or "")
    return user_content


class InferenceRequestBuilder:
    def __init__(self, prompt_center: PromptCenter) -> None:
        self.prompt_center = prompt_center

    def build(self, context: LLMContext) -> InferenceRequest:
        visible_context = context.metadata.get("visible_context")
        if not isinstance(visible_context, InferenceVisibleContext):
            raise ValueError("LLMContext metadata is missing InferenceVisibleContext.")

        if context.task == InferenceTask.ROUTE:
            inference_context = _build_router_inference_context(context, visible_context)
            text_only = bool((context.routing or {}).get("text_only_router", False))
            return InferenceRequest(
                task=context.task,
                model=resolve_model(context),
                instructions=build_router_system_prompt(self.prompt_center),
                input=_router_input(visible_context, text_only=text_only),
                history=list(context.history),
                stream=False,
                temperature=resolve_temperature(context),
                timeout=resolve_timeout(context),
                modalities=["text"],
                extra_body={
                    "metadata": {"inference_context": inference_context},
                },
                metadata={
                    "inference_context": inference_context,
                    "system_prompt": build_router_system_prompt(self.prompt_center),
                    "messages_preview": {
                        "history_count": len(context.history),
                        "has_artifacts": bool(visible_context.artifacts),
                        "has_reference_artifacts": bool(visible_context.reference_artifacts),
                        "input_type": ("list" if isinstance(_router_input(visible_context, text_only=text_only), list) else "text"),
                    },
                },
            )

        strategy_meta = dict(context.strategy or {})
        strategy = None
        plan = context.metadata.get("plan")
        if plan is not None:
            strategy = getattr(plan, "strategy", None)
        if strategy is None:
            raise ValueError("Generate context is missing plan.strategy for prompt resolution.")
        system_prompt = build_responder_system_prompt(
            prompt_center=self.prompt_center,
            visible_context=visible_context,
            strategy=strategy,
        )
        inference_context = _build_responder_inference_context(context, visible_context, strategy)
        return InferenceRequest(
            task=context.task,
            model=resolve_model(context),
            instructions=system_prompt,
            input=_generation_input(visible_context, strategy),
            history=list(context.history),
            stream=False,
            temperature=resolve_temperature(context),
            timeout=resolve_timeout(context),
            modalities=["text"],
            extra_body={
                "metadata": {"inference_context": inference_context},
            },
            metadata={
                "inference_context": inference_context,
                "system_prompt": system_prompt,
                "strategy": strategy_meta,
                "messages_preview": {
                    "history_count": len(context.history),
                    "has_artifacts": bool(visible_context.artifacts),
                    "has_reference_artifacts": bool(visible_context.reference_artifacts),
                    "input_type": ("list" if isinstance(_generation_input(visible_context, strategy), list) else "text"),
                },
            },
        )

