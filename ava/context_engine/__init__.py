"""Public entrypoint for the Context Compiler.

Only expose the primary architecture entry here.
All supporting types, helpers, and compatibility bridges must be imported
from their explicit submodules.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ava.multi_turn_context_builder.compiler import ContextCompiler as ContextCompiler

__all__ = ["ContextCompiler"]


def __getattr__(name: str):
    if name == "ContextCompiler":
        from ava.multi_turn_context_builder.compiler import ContextCompiler

        return ContextCompiler
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
