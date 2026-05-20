"""Compatibility wrapper for speech domain math IR."""

"""Minimal IR for math oralization of LaTeX spans."""


from dataclasses import dataclass, field
import re


@dataclass(frozen=True)
class MathSpeechIR:
    source_text: str
    expression_type: str
    entities: tuple[str, ...] = field(default_factory=tuple)
    structure: dict[str, object] = field(default_factory=dict)
    speech_plan: tuple[str, ...] = field(default_factory=tuple)


def build_math_speech_ir(text: str) -> MathSpeechIR:
    expression_type = _detect_expression_type(text)
    entities = tuple(_extract_entities(text))
    structure: dict[str, object] = {
        "has_latex_command": "\\" in text,
        "has_superscript": "^" in text,
        "has_subscript": "_" in text,
    }
    if expression_type == "limit":
        structure["contains_limit"] = True
    if expression_type == "piecewise":
        structure["contains_piecewise"] = True
    if expression_type == "integral":
        structure["contains_integral"] = True
    if expression_type == "summation":
        structure["contains_summation"] = True
    if expression_type == "matrix":
        structure["contains_matrix"] = True
    return MathSpeechIR(
        source_text=text,
        expression_type=expression_type,
        entities=entities,
        structure=structure,
        speech_plan=tuple(_build_speech_plan(expression_type)),
    )


def _detect_expression_type(text: str) -> str:
    lowered = text.lower()
    if "\\begin{cases}" in lowered or "cases" in lowered:
        return "piecewise"
    if "\\lim" in lowered or "\\to" in lowered:
        return "limit"
    if "\\frac" in lowered:
        return "fraction"
    if "\\sqrt" in lowered:
        return "radical"
    if "\\int" in lowered:
        return "integral"
    if "\\sum" in lowered:
        return "summation"
    if any(marker in lowered for marker in ("\\begin{matrix}", "\\begin{bmatrix}", "\\begin{pmatrix}")):
        return "matrix"
    return "equation"


def _extract_entities(text: str) -> list[str]:
    items = re.findall(r"\b[a-zA-Z]\b", text)
    seen: set[str] = set()
    deduped: list[str] = []
    for item in items:
        normalized = item.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(item)
    return deduped


def _build_speech_plan(expression_type: str) -> list[str]:
    plans = {
        "piecewise": ["先说明是分段函数", "再逐段朗读条件和值"],
        "limit": ["先读趋近条件", "再读表达式主体"],
        "fraction": ["优先用分数口语读法"],
        "radical": ["先读根号范围", "再读根号内表达式"],
        "integral": ["先读积分区间", "再读被积函数"],
        "summation": ["先读求和上下限", "再读求和项"],
        "matrix": ["先说明矩阵维度", "再按行朗读元素"],
        "equation": ["先读主表达式", "再读符号关系"],
    }
    return plans.get(expression_type, plans["equation"])
