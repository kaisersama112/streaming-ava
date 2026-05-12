"""Detect LaTeX spans embedded in otherwise normal text."""

from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class LatexSpan:
    start: int
    end: int
    raw: str
    kind: str


_COMMAND_STARTERS = ("\\frac", "\\sqrt", "\\lim", "\\sin", "\\cos", "\\tan")
_SUPERSCRIPT_CHARS = "⁰¹²³⁴⁵⁶⁷⁸⁹ⁿ"
_PLAIN_FORMULA_BOUNDARY_CHARS = set("，。；！？,.!?：:\n\t")


def detect_latex_spans(text: str) -> list[LatexSpan]:
    spans: list[LatexSpan] = []
    occupied: list[tuple[int, int]] = []

    def add_span(start: int, end: int, kind: str) -> None:
        if start < 0 or end <= start:
            return
        for left, right in occupied:
            if not (end <= left or start >= right):
                return
        spans.append(LatexSpan(start=start, end=end, raw=text[start:end], kind=kind))
        occupied.append((start, end))

    i = 0
    length = len(text)
    while i < length:
        if text.startswith("$$", i):
            end = _find_closing_delimiter(text, i + 2, "$$")
            if end != -1:
                add_span(i, end + 2, "display_math")
                i = end + 2
                continue
        if text.startswith("\\[", i):
            end = text.find("\\]", i + 2)
            if end != -1:
                add_span(i, end + 2, "display_math")
                i = end + 2
                continue
        if text.startswith("\\(", i):
            end = text.find("\\)", i + 2)
            if end != -1:
                add_span(i, end + 2, "inline_math")
                i = end + 2
                continue
        if text[i] == "$" and not text.startswith("$$", i) and not _is_escaped(text, i):
            end = _find_closing_delimiter(text, i + 1, "$")
            if end != -1:
                add_span(i, end + 1, "inline_math")
                i = end + 1
                continue
        command_end = _find_command_span_end(text, i)
        if command_end != -1:
            add_span(i, command_end, "command_math")
            i = command_end
            continue
        i += 1

    spans.sort(key=lambda span: span.start)
    return spans


def detect_formula_spans(text: str) -> list[LatexSpan]:
    spans = detect_latex_spans(text)
    occupied = [(span.start, span.end) for span in spans]

    def add_span(start: int, end: int, kind: str) -> None:
        if start < 0 or end <= start:
            return
        for left, right in occupied:
            if not (end <= left or start >= right):
                return
        raw = text[start:end]
        if not _looks_like_plain_formula(raw):
            return
        spans.append(LatexSpan(start=start, end=end, raw=raw, kind=kind))
        occupied.append((start, end))

    index = 0
    length = len(text)
    while index < length:
        if _is_formulaish_char(text[index]):
            start = index
            index += 1
            while index < length and _is_formulaish_char(text[index]):
                index += 1
            end = index
            while start < end and text[start].isspace():
                start += 1
            while end > start and text[end - 1].isspace():
                end -= 1
            if start < end:
                add_span(start, end, "plain_formula")
            continue
        index += 1

    spans.sort(key=lambda span: span.start)
    return spans


def has_unclosed_latex(text: str) -> bool:
    state = _LatexState()
    i = 0
    length = len(text)
    while i < length:
        if text.startswith("$$", i) and not _is_escaped(text, i):
            state.toggle("double_dollar")
            i += 2
            continue
        if text.startswith("\\[", i):
            state.toggle("bracket")
            i += 2
            continue
        if text.startswith("\\(", i):
            state.toggle("paren")
            i += 2
            continue
        if text.startswith("\\]", i):
            state.close("bracket")
            i += 2
            continue
        if text.startswith("\\)", i):
            state.close("paren")
            i += 2
            continue
        if text[i] == "$" and not _is_escaped(text, i):
            state.toggle("single_dollar")
            i += 1
            continue
        if state.in_math and text[i] == "{":
            state.brace_depth += 1
        elif state.in_math and text[i] == "}":
            state.brace_depth = max(0, state.brace_depth - 1)
        i += 1
    return state.in_math or state.brace_depth > 0


def _find_closing_delimiter(text: str, start: int, delimiter: str) -> int:
    i = start
    while i < len(text):
        if text.startswith(delimiter, i) and not _is_escaped(text, i):
            return i
        i += 1
    return -1


def _find_command_span_end(text: str, start: int) -> int:
    if not text.startswith(_COMMAND_STARTERS, start):
        return -1
    i = start
    brace_depth = 0
    seen_non_command = False
    while i < len(text):
        ch = text[i]
        if ch == "\\" and i + 1 < len(text):
            i += 1
            seen_non_command = True
        elif ch == "{":
            brace_depth += 1
            seen_non_command = True
        elif ch == "}":
            brace_depth -= 1
            if brace_depth <= 0 and seen_non_command:
                return i + 1
        elif brace_depth == 0 and seen_non_command and ch in " \n\t，。；！？,.;!?":
            return i
        i += 1
    return -1 if brace_depth > 0 else i


def _is_escaped(text: str, index: int) -> bool:
    backslashes = 0
    pos = index - 1
    while pos >= 0 and text[pos] == "\\":
        backslashes += 1
        pos -= 1
    return backslashes % 2 == 1


def _is_formulaish_char(ch: str) -> bool:
    if ch in _PLAIN_FORMULA_BOUNDARY_CHARS:
        return False
    if ch.isspace():
        return True
    if ch in _SUPERSCRIPT_CHARS:
        return True
    if ch in "+-*/^=<>≤≥≈≠×÷()[]{}_%√|":
        return True
    return ch.isascii() and ch.isalnum()


def _looks_like_plain_formula(text: str) -> bool:
    candidate = " ".join((text or "").split()).strip()
    if len(candidate) < 3:
        return False
    if candidate.startswith("\\"):
        return False
    if re.fullmatch(r"\d{1,4}[-/]\d{1,2}([-/]\d{1,4})?", candidate):
        return False
    has_symbol_or_digit = any(ch.isdigit() or ch in _SUPERSCRIPT_CHARS for ch in candidate)
    has_letter = any("a" <= ch.lower() <= "z" for ch in candidate)
    if not (has_symbol_or_digit or has_letter):
        return False

    strong_markers = ("=", "<", ">", "≤", "≥", "≈", "≠", "^", "√", "×", "÷")
    if any(marker in candidate for marker in strong_markers):
        return True
    if re.search(r"\d+\s*[+\-*/]\s*\d+", candidate):
        return True
    if re.search(r"[A-Za-z]\s*[+\-*/]\s*[A-Za-z0-9(]", candidate):
        return True
    if re.search(r"\d+\s*[A-Za-z(]", candidate):
        return True
    if re.search(rf"[A-Za-z0-9\)]\s*[{re.escape(_SUPERSCRIPT_CHARS)}]", candidate):
        return True
    return False


class _LatexState:
    def __init__(self) -> None:
        self.single_dollar = False
        self.double_dollar = False
        self.paren = False
        self.bracket = False
        self.brace_depth = 0

    @property
    def in_math(self) -> bool:
        return self.single_dollar or self.double_dollar or self.paren or self.bracket

    def toggle(self, kind: str) -> None:
        setattr(self, kind, not bool(getattr(self, kind)))

    def close(self, kind: str) -> None:
        setattr(self, kind, False)
