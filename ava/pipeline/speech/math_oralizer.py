"""Thin adapter around the single SymPy-backed LaTeX oralizer."""



import re

from .math_ir import MathSpeechIR, build_math_speech_ir

from .math_latex_oralizer import oralize_latex_with_trace

_SYMBOL_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("\\frac", "分式"),
    ("\\sqrt", "根号"),
    ("\\lim", "极限"),
    ("\\sum", "求和"),
    ("\\int", "积分"),
    ("\\to", "趋近于"),
    ("\\leq", "小于等于"),
    ("\\geq", "大于等于"),
    ("\\neq", "不等于"),
    ("\\times", "乘"),
    ("\\cdot", "乘"),
    ("\\div", "除以"),
    ("=", "等于"),
    ("+", "加"),
    ("-", "减"),
    ("*", "乘"),
    ("/", "除以"),
    ("^", "的幂"),
    ("_", "下标"),
    ("(", ""),
    (")", ""),
    ("[", ""),
    ("]", ""),
    ("{", ""),
    ("}", ""),
    ("<", "小于"),
    (">", "大于"),
    ("≤", "小于等于"),
    ("≥", "大于等于"),
    ("≠", "不等于"),
    ("≈", "约等于"),
    ("π", "派"),
    ("∞", "无穷大"),
)


def oralize_formula_span(raw: str) -> tuple[str, MathSpeechIR]:
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
        if spoken and spoken != inner:
            return spoken, ir
    except Exception as exc:
        ir.structure["oralizer_backend"] = "math_latex_oralizer"
        ir.structure["oralizer_mode"] = "adapter_error"
        ir.structure["oralizer_fallback_used"] = True
        ir.structure["oralizer_fallback_reason"] = f"{type(exc).__name__}: {exc}"

    fallback = _heuristic_oralize_formula(inner)
    ir.structure["oralizer_backend"] = "local_formula_fallback"
    ir.structure["oralizer_mode"] = "heuristic_formula"
    ir.structure["oralizer_fallback_used"] = True
    if "oralizer_fallback_reason" not in ir.structure:
        ir.structure["oralizer_fallback_reason"] = "heuristic_formula_fallback"
    ir.structure["normalized_text"] = inner
    return fallback or inner, ir


def oralize_latex_span(raw: str) -> tuple[str, MathSpeechIR]:
    return oralize_formula_span(raw)


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


def _heuristic_oralize_formula(text: str) -> str:
    spoken = str(text or "").strip()
    if not spoken:
        return spoken

    spoken = re.sub(r"([A-Za-z0-9])\^([A-Za-z0-9]+)", r"\1 的 \2 次方", spoken)
    spoken = re.sub(r"([A-Za-z0-9])_([A-Za-z0-9]+)", r"\1 下标 \2", spoken)
    spoken = re.sub(r"(\d)([A-Za-z])", r"\1 乘 \2", spoken)
    spoken = re.sub(r"([A-Za-z])(\d)", r"\1 \2", spoken)

    for source, target in _SYMBOL_REPLACEMENTS:
        spoken = spoken.replace(source, f" {target} ")

    spoken = re.sub(r"\s+", " ", spoken).strip()
    return spoken
