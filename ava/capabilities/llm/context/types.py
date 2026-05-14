from dataclasses import dataclass, field
from typing import Any

from ava.domain.multimodal.media import MediaArtifact, TurnInput


@dataclass(frozen=True)
class InferenceVisibleContext:
    """推理阶段模型可见的上下文快照。"""

    # 当前轮次的标准化输入对象，包含文本、多模态摘要、附件等信息
    turn_input: TurnInput

    # 当前轮次的用户文本；通常来自 normalized_text，必要时由 multimodal_summary 兜底
    user_text: str

    # 当前会话 ID，用于标识一次完整会话
    session_id: str

    # 会话级场景标识，表示整个会话当前所属的场景
    session_scene: str

    # 当前轮次场景标识，表示本轮输入被归类到的具体场景
    turn_scene: str

    # 模型可见的历史消息列表，通常为 OpenAI messages 格式
    history_messages: list[dict[str, Any]]

    # 当前轮次直接携带的附件，如图片、文件、音频等
    artifacts: tuple[MediaArtifact, ...]

    # 从历史上下文中继承来的参考附件，用于处理“继续”“这个呢”等承接式追问
    reference_artifacts: tuple[MediaArtifact, ...]

    # 原始 turn records，用于调试、追踪或后续上下文重建
    turn_records: list[dict[str, Any]]

    # 上下文配置档位，例如 router、responder_minimal、full 等
    context_profile: str = "full"

    # 标识 reference_artifacts 是否由历史上下文继承而来
    reference_artifacts_inherited: bool = False

    # 路由阶段使用或生成的附件简报，用于减少重复多模态读取
    router_artifact_brief: dict[str, Any] = field(default_factory=dict)

    # 路由阶段生成的计划信息，用于传递给后续响应或执行阶段
    router_plan: dict[str, Any] = field(default_factory=dict)
