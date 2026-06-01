"""只负责把公式文本转换为更适合朗读的文本。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from configs import settings

from ava.pipeline.speech.latex_span_detector import LatexSpan, detect_formula_spans
from ava.pipeline.speech.math_oralizer import oralize_formula_span


@dataclass(frozen=True)
class SpeechBuildResult:
    display_text: str
    speech_text: str
    speech_segments: tuple[str, ...] = ()
    trace: dict[str, Any] = field(default_factory=dict)


def should_apply_math_oralizer() -> bool:
    cfg = settings.speech_postprocess
    if not (cfg.enabled and cfg.math_oralizer_enabled):
        return False
    return True


def build_speech_text(
    reply_text: str,
    snapshot: Any | None = None,
) -> SpeechBuildResult:
    del snapshot
    if not reply_text:
        return SpeechBuildResult(display_text=reply_text, speech_text=reply_text)
    if not should_apply_math_oralizer():
        return SpeechBuildResult(display_text=reply_text, speech_text=reply_text)

    spans = detect_formula_spans(reply_text)
    if not spans:
        return SpeechBuildResult(
            display_text=reply_text,
            speech_text=reply_text,
            trace={
                "enabled": True,
                "formula_spans": 0,
                "latex_spans": 0,
                "plain_formula_spans": 0,
                "replacements": [],
            },
        )

    speech_text, replacements = _replace_spans(reply_text, spans)
    latex_span_count = sum(1 for span in spans if span.kind != "plain_formula")
    plain_formula_span_count = sum(1 for span in spans if span.kind == "plain_formula")
    return SpeechBuildResult(
        display_text=reply_text,
        speech_text=speech_text,
        speech_segments=(speech_text,) if speech_text else (),
        trace={
            "enabled": True,
            "formula_spans": len(spans),
            "latex_spans": latex_span_count,
            "plain_formula_spans": plain_formula_span_count,
            "replacements": replacements,
        },
    )


def _replace_spans(text: str, spans: list[LatexSpan]) -> tuple[str, list[dict[str, Any]]]:
    parts: list[str] = []
    replacements: list[dict[str, Any]] = []
    cursor = 0
    for span in spans:
        parts.append(text[cursor:span.start])
        spoken, ir = oralize_formula_span(span.raw)
        parts.append(spoken)
        replacements.append(
            {
                "kind": span.kind,
                "raw": span.raw,
                "spoken": spoken,
                "expression_type": ir.expression_type,
                "oralizer_backend": ir.structure.get("oralizer_backend", ""),
                "oralizer_mode": ir.structure.get("oralizer_mode", ""),
                "oralizer_fallback_used": bool(ir.structure.get("oralizer_fallback_used", False)),
                "oralizer_fallback_reason": str(ir.structure.get("oralizer_fallback_reason", "") or ""),
                "normalized_text": str(ir.structure.get("normalized_text", "") or ""),
            }
        )
        cursor = span.end
    parts.append(text[cursor:])
    return "".join(parts), replacements
