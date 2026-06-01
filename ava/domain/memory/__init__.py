"""Memory module public API."""

from __future__ import annotations

__all__ = [
    "MessageBlockMemoryEntry",
    "MessageBlockMemoryStore",
    "EducationMemory",
    "MemoryProjection",
    "MemoryProjector",
    "MemoryRetriever",
    "RetrievedMemory",
    "SessionMemory",
    "SummaryMemory",
]


def __getattr__(name: str):
    if name in {"MessageBlockMemoryEntry", "MemoryProjection", "RetrievedMemory"}:
        from . import types as types_module

        return getattr(types_module, name)
    if name == "MessageBlockMemoryStore":
        from .message_blocks import MessageBlockMemoryStore

        return MessageBlockMemoryStore
    if name == "EducationMemory":
        from .education import EducationMemory

        return EducationMemory
    if name == "MemoryProjector":
        from .projector import MemoryProjector

        return MemoryProjector
    if name == "MemoryRetriever":
        from .retriever import MemoryRetriever

        return MemoryRetriever
    if name == "SessionMemory":
        from .session_memory import SessionMemory

        return SessionMemory
    if name == "SummaryMemory":
        from .summaries import SummaryMemory

        return SummaryMemory
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
