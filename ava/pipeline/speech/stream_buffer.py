"""Latex-aware buffer for streaming TTS submission."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from ava.pipeline.speech.latex_span_detector import has_unclosed_latex
from ava.pipeline.speech.text_builder import build_speech_text

_BOUNDARY_CHARS = ".!?;,:。\n！？；，、："


@dataclass
class LatexAwareSpeechBuffer:
    flush_chars: int = 72

    def __post_init__(self) -> None:
        self._buffer = ""
        self._hard_flush_chars = max(self.flush_chars + 24, self.flush_chars * 2)
        self._stats: dict[str, Any] = {
            "chunks_built": 0,
            "formula_spans": 0,
            "latex_spans": 0,
            "plain_formula_spans": 0,
            "replacements": 0,
            "last_trace": {},
        }

    def push(self, token: str) -> list[str]:
        if not token:
            return []
        self._buffer += token
        return self._drain_ready_chunks()

    def flush_final(self) -> list[str]:
        if not self._buffer.strip():
            self._buffer = ""
            return []
        return self._flush(force=True)

    def snapshot(self) -> dict[str, Any]:
        return {
            "buffer_chars": len(self._buffer),
            "flush_chars": self.flush_chars,
            "hard_flush_chars": self._hard_flush_chars,
            **dict(self._stats),
        }

    def _drain_ready_chunks(self) -> list[str]:
        chunks: list[str] = []
        while self._should_flush():
            chunk = self._flush_one()
            if not chunk:
                break
            chunks.append(chunk)
        return chunks

    def _should_flush(self) -> bool:
        stripped = self._buffer.strip()
        if not stripped:
            return False
        if _is_punctuation_only(stripped):
            return False
        if has_unclosed_latex(self._buffer):
            return False
        if _has_boundary(stripped):
            return True
        return len(stripped) >= self._hard_flush_chars

    def _flush(self, *, force: bool = False) -> list[str]:
        if not force and has_unclosed_latex(self._buffer):
            return []
        raw = self._buffer
        self._buffer = ""
        built = build_speech_text(raw)
        self._record_trace(built.trace)
        spoken = built.speech_text.strip()
        return [spoken] if spoken else []

    def _flush_one(self) -> str:
        split_index = _find_split_index(self._buffer, self.flush_chars)
        if split_index <= 0:
            if len(self._buffer.strip()) < self._hard_flush_chars and not _has_boundary(self._buffer.strip()):
                return ""
            raw = self._buffer
            self._buffer = ""
        else:
            raw = self._buffer[:split_index]
            self._buffer = self._buffer[split_index:]
        built = build_speech_text(raw)
        self._record_trace(built.trace)
        return built.speech_text.strip()

    def _record_trace(self, trace: dict[str, Any]) -> None:
        trace = dict(trace or {})
        self._stats["chunks_built"] = int(self._stats.get("chunks_built", 0) or 0) + 1
        self._stats["formula_spans"] = int(self._stats.get("formula_spans", 0) or 0) + int(trace.get("formula_spans", 0) or 0)
        self._stats["latex_spans"] = int(self._stats.get("latex_spans", 0) or 0) + int(trace.get("latex_spans", 0) or 0)
        self._stats["plain_formula_spans"] = int(self._stats.get("plain_formula_spans", 0) or 0) + int(trace.get("plain_formula_spans", 0) or 0)
        replacements = trace.get("replacements") or []
        self._stats["replacements"] = int(self._stats.get("replacements", 0) or 0) + len(replacements)
        self._stats["last_trace"] = trace


def _has_boundary(text: str) -> bool:
    return bool(text) and text[-1] in _BOUNDARY_CHARS


def _is_punctuation_only(text: str) -> bool:
    return bool(text) and all(ch in _BOUNDARY_CHARS or ch.isspace() for ch in text)


def _find_split_index(text: str, flush_chars: int) -> int:
    stripped = text.strip()
    if not stripped:
        return 0
    if _has_boundary(stripped):
        return len(text)
    if len(stripped) < flush_chars:
        return 0
    boundaries = [index + 1 for index, ch in enumerate(text) if ch in _BOUNDARY_CHARS]
    soft_boundaries = [match.end() for match in re.finditer(r"\s", text)]
    candidates = [idx for idx in boundaries if idx >= flush_chars]
    if candidates:
        return candidates[0]
    candidates = [idx for idx in boundaries if idx >= max(8, flush_chars // 2)]
    if candidates:
        return candidates[-1]
    candidates = [idx for idx in soft_boundaries if idx >= flush_chars]
    if candidates:
        return candidates[0]
    return 0
