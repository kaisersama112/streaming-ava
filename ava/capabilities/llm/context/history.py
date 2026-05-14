from typing import Any


def _artifact_labels(raw_artifacts: list[dict[str, object]]) -> list[str]:
    """将原始附件信息转换为可读的附件标签列表。"""

    labels: list[str] = []

    for artifact in raw_artifacts:
        # 附件类型，默认为 file；使用 strip 清理空白字符
        kind = str(artifact.get("kind", "file") or "file").strip()

        # 附件名称，可能为空
        name = str(artifact.get("name", "") or "").strip()

        # 附件摘要，可能来自上游多模态分析或 metadata
        summary = str(artifact.get("summary", "") or "").strip()

        # 构造基础标签，例如：[image] demo.png
        base = f"[{kind}] {name}".strip()

        # 如果存在摘要，且摘要与名称不同，则将摘要附加到标签后
        if summary and summary != name:
            labels.append(f"{base}: {summary}" if base else summary)

        # 否则仅保留基础标签
        elif base:
            labels.append(base)

    return labels


def record_to_history_messages(record: dict[str, object]) -> list[dict[str, str]]:
    """将单条 turn record 转换为模型可见的历史消息。"""

    messages: list[dict[str, str]] = []

    # 用户在该轮中的文本输入
    user_text = str(record.get("user_text", "") or "").strip()

    # 多模态摘要；当没有文本输入时作为兜底内容
    multimodal_summary = str(record.get("multimodal_summary", "") or "").strip()

    # 将该轮中的附件信息转换为文本化标签
    artifact_lines = _artifact_labels(list(record.get("artifacts") or []))

    # 同时存在用户文本和附件时，将附件作为“参考附件”附加到用户消息后
    if user_text and artifact_lines:
        user_content = (
            f"{user_text}\n参考附件：\n"
            + "\n".join(f"- {label}" for label in artifact_lines)
        )

    # 仅存在用户文本时，直接使用用户文本
    elif user_text:
        user_content = user_text

    # 仅存在附件时，将附件列表作为用户消息内容
    elif artifact_lines:
        user_content = (
            "参考附件：\n"
            + "\n".join(f"- {label}" for label in artifact_lines)
        )

    # 文本和附件都不存在时，使用多模态摘要兜底
    else:
        user_content = multimodal_summary

    # 写入用户消息
    if user_content:
        messages.append({"role": "user", "content": user_content})

    # 读取轮次状态；默认按 completed 处理
    turn_status = str(record.get("turn_status", "completed") or "completed").strip()

    # completed 和 interrupted 状态下保留 assistant_text：
    # - completed：正常完成的助手回复
    # - interrupted：虽然中断，但已有部分回复可作为历史上下文
    assistant_text = (
        str(record.get("assistant_text", "") or "").strip()
        if turn_status in {"completed", "interrupted"}
        else ""
    )

    # 写入 assistant 消息
    if assistant_text:
        messages.append({"role": "assistant", "content": assistant_text})

    return messages


def build_visible_history(
    turn_records: list[dict[str, Any]],
    *,
    max_messages: int,
) -> list[dict[str, Any]]:
    """根据 turn records 构建最终传入模型的可见历史消息。"""

    # 展平所有 turn records：
    # 每条 record 可能生成 user 与 assistant 两条消息
    flattened: list[dict[str, Any]] = []

    for record in turn_records:
        flattened.extend(record_to_history_messages(record))

    # 只保留最近 max_messages 条消息，控制上下文长度
    return flattened[-max_messages:]