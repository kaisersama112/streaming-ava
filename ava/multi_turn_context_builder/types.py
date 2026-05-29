"""多轮上下文构造模块的核心类型定义。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ava.domain.multimodal.media import MediaArtifact, TurnInput


@dataclass(frozen=True)
class ContextSession:
    """会话级元信息。"""

    session_id: str
    session_scene: str
    turn_scene: str
    profile: str = "full"


@dataclass(frozen=True)
class ContextTurn:
    """当前轮输入信息。"""

    turn_input: TurnInput
    user_text: str
    artifacts: tuple[MediaArtifact, ...] = ()


@dataclass(frozen=True)
class ConversationContext:
    """只承载当前轮构造所需的最小上下文本体。"""

    session: ContextSession
    current: ContextTurn
    conversation: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class ConversationBuildOptions:
    """构建会话上下文时使用的选项。"""

    history_window: int
    current_turn_id: int | None = None
    max_context_messages: int | None = None
    profile: str = "full"


@dataclass(frozen=True)
class CompiledInstructions:
    """单个模型阶段使用的 instructions 编译结果。"""

    phase: str
    text: str
    active_skills: list[str] = field(default_factory=list)
    sections: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SkillSelection:
    """编译阶段选中的单个技能片段。"""

    skill_id: str
    title: str
    instruction_fragment: str
    source_kind: str = "builtin"
    source_path: str | None = None


@dataclass(frozen=True)
class CompiledConversationPayload:
    """面向模型输入的最终上下文载荷。"""

    instructions: str
    input: list[dict[str, Any]]
    context: ConversationContext
    active_skills: list[str] = field(default_factory=list)
    sections: dict[str, Any] = field(default_factory=dict)
