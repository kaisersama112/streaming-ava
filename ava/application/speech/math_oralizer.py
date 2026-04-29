"""Thin adapter around the single SymPy-backed LaTeX oralizer."""

from __future__ import annotations

from .math_latex_oralizer import oralize_latex_with_trace
from .math_ir import MathSpeechIR, build_math_speech_ir


def oralize_latex_span(raw: str) -> tuple[str, MathSpeechIR]:
    inner = _strip_math_delimiters(raw).strip()
    ir = build_math_speech_ir(inner)
    if not inner:
        return inner, ir
    try:
        spoken, oralizer_trace = oralize_latex_with_trace(inner)
        ir.structure["oralizer_backend"] = str(oralizer_trace.get("backend", "math_latex_oralizer"))
        ir.structure["oralizer_mode"] = str(oralizer_trace.get("mode", "unknown"))
        ir.structure["oralizer_fallback_used"] = bool(oralizer_trace.get("fallback_used", False))
        if oralizer_trace.get("fallback_reason"):
            ir.structure["oralizer_fallback_reason"] = str(oralizer_trace.get("fallback_reason"))
        if oralizer_trace.get("normalized_text"):
            ir.structure["normalized_text"] = str(oralizer_trace.get("normalized_text"))
        spoken = spoken.strip()
    except Exception as exc:
        ir.structure["oralizer_backend"] = "math_latex_oralizer"
        ir.structure["oralizer_mode"] = "adapter_error"
        ir.structure["oralizer_fallback_used"] = True
        ir.structure["oralizer_fallback_reason"] = f"{type(exc).__name__}: {exc}"
        spoken = inner
    return spoken or inner, ir


def _strip_math_delimiters(text: str) -> str:
    pairs = [
        ("$$", "$$"),
        ("\\[", "\\]"),
        ("\\(", "\\)"),
        ("$", "$"),
    ]
    for left, right in pairs:
        if text.startswith(left) and text.endswith(right) and len(text) >= len(left) + len(right):
            return text[len(left):len(text) - len(right)]
    return text
