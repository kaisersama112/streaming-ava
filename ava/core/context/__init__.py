"""Core context primitives."""

from ava.core.context.continuity import (
    build_artifact_brief_for_context,
    select_router_model,
    should_inherit_reference_artifacts,
    should_isolate_current_artifact_context,
)
from ava.core.context.input import AttachmentPayload, build_turn_input
from ava.core.context.snapshot import build_context_snapshot

__all__ = [
    "AttachmentPayload",
    "build_artifact_brief_for_context",
    "build_context_snapshot",
    "build_turn_input",
    "select_router_model",
    "should_inherit_reference_artifacts",
    "should_isolate_current_artifact_context",
]
