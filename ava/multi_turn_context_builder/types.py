"""多轮上下文构造模块的核心类型定义。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ContextSession:
    """会话级元信息。"""

    session_id: str
    session_scene: str
    turn_scene: str
    profile: str = "full"


@dataclass(frozen=True)
class ContextTurn:
    """当前轮最小输入信息。"""

    user_message: dict[str, Any]


@dataclass(frozen=True)
class ConversationContext:
    """最小对话上下文本体。

    这里只保留：
    - 会话元信息
    - 当前轮 user message
    - 可见多轮消息数组
    """

    session: ContextSession
    current: ContextTurn
    conversation: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class ConversationBuildOptions:
    """构建上下文时的选项。"""

    history_window: int
    current_turn_id: int | None = None
    max_context_messages: int | None = None
    profile: str = "full"


@dataclass(frozen=True)
class CompiledInstructions:
    """单阶段指令编译结果。"""

    phase: str
    text: str
    active_skills: list[str] = field(default_factory=list)
    sections: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CompiledContext:
    """分层编译结果：system / developer(runtime) / history / user。"""

    system: str
    developer: str
    history: list[dict[str, Any]] = field(default_factory=list)
    user: dict[str, Any] = field(default_factory=dict)

    def render_instructions(self) -> str:
        parts = [part for part in (self.system.strip(), self.developer.strip()) if part]
        return "\n\n".join(parts)

    def render_input(self) -> list[dict[str, Any]]:
        return [*self.history, dict(self.user)]

    def to_layers(self) -> dict[str, Any]:
        return {
            "system": self.system,
            "developer": self.developer,
            "history": list(self.history),
            "user": dict(self.user),
        }


@dataclass(frozen=True)
class CompiledConversationPayload:
    """最终传给模型的一轮载荷。"""

    instructions: str
    input: list[dict[str, Any]]
    context: ConversationContext
    active_skills: list[str] = field(default_factory=list)
    sections: dict[str, Any] = field(default_factory=dict)
    layers: dict[str, Any] = field(default_factory=dict)
