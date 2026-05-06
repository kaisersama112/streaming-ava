"""Common responder-message builder for the model-planned turn pipeline."""

from __future__ import annotations

from ava.domain.context import ContextSnapshot
from ava.domain.strategy import BranchStrategy
from ava.infrastructure.prompts import PromptCenter, build_responder_system_prompt


def _should_include_history_messages(strategy: BranchStrategy) -> bool:
    analysis = dict(getattr(strategy, "analysis", {}) or {})
    context_policy = dict(analysis.get("prompt_context_policy", {}) or {})
    return bool(context_policy.get("include_history_messages", True))


def _should_attach_reference_artifacts(snapshot: ContextSnapshot, strategy: BranchStrategy) -> bool:
    if snapshot.artifacts or not snapshot.reference_artifacts:
        return False

    artifact_brief = dict(getattr(snapshot, "router_artifact_brief", {}) or {})
    if artifact_brief:
        if bool(artifact_brief.get("followup_requires_visual_reread", False)):
            return True
        return False

    analysis = dict(getattr(strategy, "analysis", {}) or {})
    continuity = dict(analysis.get("continuity", {}) or {})
    education_turn_frame = dict(analysis.get("education_turn_frame", {}) or {})
    scenario_policy = dict(education_turn_frame.get("scenario_policy", {}) or {})
    learning_objects = set(str(item).strip() for item in (education_turn_frame.get("learning_objects") or []) if str(item).strip())
    return bool(
        continuity.get("carry_reference_artifacts")
        or scenario_policy.get("answer_boundary") == "contextual_only"
        or "lesson_segment" in learning_objects
    )


def build_responder_messages(
    prompt_center: PromptCenter,
    snapshot: ContextSnapshot,
    strategy: BranchStrategy,
) -> list[dict[str, object]]:
    system_prompt = build_responder_system_prompt(
        prompt_center=prompt_center,
        snapshot=snapshot,
        strategy=strategy,
    )
    user_content: list[dict[str, object]] = []
    text = snapshot.turn_input.normalized_text()
    if text:
        user_content.append({"type": "text", "text": text})

    for artifact in snapshot.artifacts:
        block = artifact.to_message_block()
        if block:
            user_content.append(block)

    if _should_attach_reference_artifacts(snapshot, strategy):
        user_content.append(
            {
                "type": "text",
                "text": "请继续结合我之前上传的参考图片来回答当前问题，除非当前问题明确切换了对象。",
            }
        )
        for artifact in snapshot.reference_artifacts:
            block = artifact.to_message_block()
            if block:
                user_content.append(block)
    elif snapshot.reference_artifacts and snapshot.router_artifact_brief:
        user_content.append(
            {
                "type": "text",
                "text": "请直接基于之前题图的结构化理解和最近对话继续回答，不要要求我重新上传同一张图片。",
            }
        )

    if not user_content:
        user_content.append({"type": "text", "text": snapshot.multimodal_summary or snapshot.user_text})

    messages: list[dict[str, object]] = [{"role": "system", "content": system_prompt}]
    if _should_include_history_messages(strategy) and snapshot.history_messages:
        messages.extend(snapshot.history_messages)
    if len(user_content) == 1 and user_content[0].get("type") == "text":
        content: object = user_content[0]["text"]
    else:
        content = user_content
    messages.append({"role": "user", "content": content})
    return messages
