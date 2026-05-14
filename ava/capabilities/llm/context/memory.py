from typing import Any

from ava.domain.conversation.state import ConversationState


def build_memory_projection(state: ConversationState) -> dict[str, Any]:
    """从会话状态中提取模型可见的记忆投影。"""

    # 取出会话记忆对象，后续字段均从该对象中读取
    memory = state.memory

    return {
        # 长期或阶段性事实信息；转为 dict，避免直接暴露内部可变对象
        "facts": dict(getattr(memory, "facts", {}) or {}),

        # 最近讨论过的话题列表；转为 list，避免外部修改原始 memory 数据
        "recent_topics": list(getattr(memory, "recent_topics", []) or []),

        # 文本对话上下文摘要；清理首尾空白，避免污染 prompt
        "context_summary": str(
            getattr(memory, "context_summary", "") or ""
        ).strip(),

        # 多模态上下文摘要；用于保留图片、文件等非纯文本输入的历史概括
        "multimodal_context_summary": str(
            getattr(memory, "multimodal_context_summary", "") or ""
        ).strip(),

        # 教育场景相关状态，例如上一策略、上一 policy、学习场景等
        "education_state": dict(
            getattr(memory, "education_state", {}) or {}
        ),
    }