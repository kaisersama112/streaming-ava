from typing import Any

from ava.domain.conversation.state import ConversationState


def build_memory_projection(state: ConversationState) -> dict[str, Any]:
    memory = state.memory
    return {
        "facts": dict(getattr(memory, "facts", {}) or {}),
        "recent_topics": list(getattr(memory, "recent_topics", []) or []),
        "context_summary": str(getattr(memory, "context_summary", "") or "").strip(),
        "multimodal_context_summary": str(getattr(memory, "multimodal_context_summary", "") or "").strip(),
        "education_state": dict(getattr(memory, "education_state", {}) or {}),
    }

