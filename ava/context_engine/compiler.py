"""旧上下文编译器入口，转发到 `ava.multi_turn_context_builder.compiler`。"""

from ava.multi_turn_context_builder.compiler import (
    ContextCompiler,
    ContextContinuityPolicy,
)

__all__ = [
    "ContextCompiler",
    "ContextContinuityPolicy",
]
