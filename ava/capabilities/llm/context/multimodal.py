from typing import Any

from ava.domain.conversation.strategy import BranchStrategy
from ava.capabilities.llm.context.types import InferenceVisibleContext


def build_multimodal_projection(visible_context: InferenceVisibleContext) -> dict[str, Any]:
    return {
        "artifacts_count": len(visible_context.artifacts),
        "reference_artifacts_count": len(visible_context.reference_artifacts),
        "reference_artifacts_inherited": bool(visible_context.reference_artifacts_inherited),
        "router_artifact_brief": dict(visible_context.router_artifact_brief or {}),
    }


def should_attach_reference_artifacts(visible_context: InferenceVisibleContext, strategy: BranchStrategy | None) -> bool:
    if visible_context.artifacts or not visible_context.reference_artifacts or strategy is None:
        return False

    artifact_brief = dict(getattr(visible_context, "router_artifact_brief", {}) or {})
    if artifact_brief:
        if bool(artifact_brief.get("followup_requires_visual_reread", False)):
            return True
        return False

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


def artifacts_to_blocks(artifacts) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for artifact in list(artifacts or []):
        block = artifact.to_message_block()
        if block:
            blocks.append(block)
    return blocks
