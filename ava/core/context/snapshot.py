"""构建用于路由与响应的上下文快照。"""

from __future__ import annotations

from ava.core.context.continuity import (
    build_artifact_brief_for_context,
    should_inherit_reference_artifacts,
)
from ava.core.context.input import build_turn_input
from ava.domain.multimodal.media import TurnInput
from ava.domain.conversation.models import ContextSnapshot
from ava.domain.conversation.state import ConversationState


def _artifact_labels(raw_artifacts: list[dict[str, object]]) -> list[str]:
    """将原始附件信息转换为面向上下文展示的文本标签。"""

    labels: list[str] = []

    for artifact in raw_artifacts:
        # 附件类型，默认为 file；去除空白，避免出现脏数据
        kind = str(artifact.get("kind", "file") or "file").strip()

        # 附件名称，可能为空
        name = str(artifact.get("name", "") or "").strip()

        # 附件摘要，可能由多模态理解或上游处理生成
        summary = str(artifact.get("summary", "") or "").strip()

        # 基础标签格式，例如：[image] screenshot.png
        base = f"[{kind}] {name}".strip()

        # 如果存在摘要，且摘要不等于名称，则附加摘要说明
        if summary and summary != name:
            labels.append(f"{base}: {summary}" if base else summary)

        # 否则仅保留基础标签
        elif base:
            labels.append(base)

    return labels


def _record_to_history_messages(record: dict[str, object]) -> list[dict[str, str]]:
    """将单条 turn record 转换为 OpenAI 风格的 history messages。"""

    messages: list[dict[str, str]] = []

    # 当前历史轮次中的用户文本
    user_text = str(record.get("user_text", "") or "").strip()

    # 当前历史轮次中的多模态摘要，通常用于没有纯文本输入时兜底
    multimodal_summary = str(record.get("multimodal_summary", "") or "").strip()

    # 将历史轮次中的附件转换为文本标签
    artifact_lines = _artifact_labels(list(record.get("artifacts") or []))

    # 优先保留用户文本，并在其后附加参考附件信息
    if user_text and artifact_lines:
        user_content = (
            f"{user_text}\n参考附件：\n"
            + "\n".join(f"- {label}" for label in artifact_lines)
        )

    # 仅存在用户文本时，直接使用用户文本
    elif user_text:
        user_content = user_text

    # 仅存在附件时，将附件作为用户侧参考信息写入历史
    elif artifact_lines:
        user_content = (
            "参考附件：\n"
            + "\n".join(f"- {label}" for label in artifact_lines)
        )

    # 如果没有文本和附件，则使用多模态摘要兜底
    else:
        user_content = multimodal_summary

    # 写入用户消息
    if user_content:
        messages.append({"role": "user", "content": user_content})

    # 只有已完成的轮次才把 assistant 回复加入历史，避免引入未完成或异常输出
    turn_status = str(record.get("turn_status", "completed") or "completed").strip()
    assistant_text = (
        str(record.get("assistant_text", "") or "").strip()
        if turn_status == "completed"
        else ""
    )

    # 写入 assistant 消息
    if assistant_text:
        messages.append({"role": "assistant", "content": assistant_text})

    return messages


def build_context_snapshot(
    state: ConversationState,
    turn_input: TurnInput | str,
    history_window: int,
    current_turn_id: int | None = None,
    max_context_messages: int | None = None,
    profile: str = "full",
    include_reference_artifacts: bool | None = None,
) -> ContextSnapshot:
    """基于当前会话状态和本轮输入，构建 ContextSnapshot。"""

    # 如果调用方直接传入字符串，则先转换为标准 TurnInput
    if isinstance(turn_input, str):
        turn_input = build_turn_input(turn_input)

    # 最大上下文消息数：
    # - 如果显式传入 max_context_messages，则使用该值
    # - 否则按 history_window * 2 估算，因为一轮通常包含 user + assistant 两条消息
    # - 至少保留 2 条消息
    max_messages = max(2, int(max_context_messages or (history_window * 2)))

    # 如果没有指定当前 turn_id，则直接取最近若干条 turn records
    if current_turn_id is None:
        turn_records = state.turn_records[-max_messages:]

    # 如果指定了当前 turn_id，则从历史中排除当前轮，避免当前输入重复进入历史上下文
    else:
        turn_records = [
            item
            for item in state.turn_records
            if item.get("turn_id") != current_turn_id
        ][-max_messages:]

    # 将 turn records 展平为标准 history messages
    flattened_history: list[dict[str, str]] = []
    for record in turn_records:
        flattened_history.extend(_record_to_history_messages(record))

    # 再次按 max_messages 截断，确保最终传入模型的历史消息数量受控
    sanitized_history = flattened_history[-max_messages:]

    # 当前用户文本：
    # - 优先使用标准化文本
    # - 如果没有文本，则使用多模态摘要
    user_text = turn_input.normalized_text() or turn_input.multimodal_summary()

    # 判断是否允许继承参考附件：
    # - include_reference_artifacts 为 None 时，由连续性策略自动判断
    # - 否则使用调用方显式传入的布尔值
    allow_reference_artifacts = (
        should_inherit_reference_artifacts(state, turn_input)
        if include_reference_artifacts is None
        else bool(include_reference_artifacts)
    )

    # 默认不继承参考附件
    reference_artifacts = ()

    # 只有在允许继承，且当前输入没有新附件时，才从最近历史中继承参考附件
    if allow_reference_artifacts and not turn_input.artifacts:
        reference_artifacts = state.recent_reference_artifacts(
            current_turn_id=current_turn_id,
            limit_turns=1,
        )

    # 构建 artifact 简报，供路由器或后续响应逻辑快速判断附件上下文
    artifact_brief = build_artifact_brief_for_context(
        state,
        current_artifacts=turn_input.artifacts,
        reference_artifacts=reference_artifacts,
    )

    # 返回完整上下文快照
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
        context_profile=profile,
        reference_artifacts_inherited=bool(reference_artifacts),
        router_artifact_brief=artifact_brief,
        router_plan={},
    )