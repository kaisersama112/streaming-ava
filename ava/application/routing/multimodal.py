"""Helpers that build router messages with native multimodal content blocks."""

from __future__ import annotations

from ava.domain.context import ContextSnapshot
from ava.infrastructure.prompts import PromptCenter, build_router_system_prompt, build_router_user_message


def build_router_messages(
    prompt_center: PromptCenter,
    snapshot: ContextSnapshot,
    *,
    text_only: bool = False,
    artifact_brief: dict[str, object] | None = None,
    text_brief: dict[str, object] | None = None,
) -> list[dict[str, object]]:
    messages: list[dict[str, object]] = [
        {"role": "system", "content": build_router_system_prompt(prompt_center)},
    ]
    # 插入历史对话记录
    if snapshot.history_messages:
        messages.extend(snapshot.history_messages)
    # 追加当前轮次的 user 消息
    messages.append(build_router_user_message(snapshot, text_only=text_only, artifact_brief=artifact_brief, text_brief=text_brief))
    return messages
