"""Domain-level context snapshots shared across application services."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ava.domain.multimodal.media import MediaArtifact, TurnInput


@dataclass(frozen=True)
class ContextSnapshot:
    # 当前轮次的原始输入对象，通常包含用户输入、上下文元信息等
    turn_input: TurnInput

    # 当前轮次用户输入的文本内容
    user_text: str

    # 会话 ID，用于标识一次完整对话会话
    session_id: str

    # 会话级场景标识，表示整个会话所属的业务场景或上下文场景
    session_scene: str

    # 当前轮次的场景标识，表示本轮交互所属的具体场景
    turn_scene: str

    # 历史消息列表，保存此前对话中的消息记录
    history_messages: list[dict[str, Any]]

    # 当前轮次关联的媒体产物，如图片、文件、音频等
    artifacts: tuple[MediaArtifact, ...]

    # 当前轮次引用的媒体产物，通常来自用户显式引用或系统检索得到的资源
    reference_artifacts: tuple[MediaArtifact, ...]

    # 当前轮次相关的结构化记录列表，可用于追踪状态、路由结果或处理过程
    turn_records: list[dict[str, Any]]

    # 上下文配置档位，默认为 "full"，表示使用完整上下文
    context_profile: str = "full"

    # 标识 reference_artifacts 是否从上一轮或会话上下文中继承而来
    reference_artifacts_inherited: bool = False

    # 路由器生成的产物摘要信息，用于描述当前轮次可用或相关的 artifact
    router_artifact_brief: dict[str, Any] = field(default_factory=dict)

    # 路由器生成的处理计划，用于记录后续执行策略、工具选择或任务分解
    router_plan: dict[str, Any] = field(default_factory=dict)