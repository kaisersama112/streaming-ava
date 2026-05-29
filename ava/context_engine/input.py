"""旧输入装配入口，转发到 `ava.multi_turn_context_builder.input`。"""

from ava.multi_turn_context_builder.input import AttachmentPayload, TurnInputAssembler

__all__ = [
    "AttachmentPayload",
    "TurnInputAssembler",
]
