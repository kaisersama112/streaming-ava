"""Parses structured JSON out of Router LLM output."""

from __future__ import annotations

import json


def extract_json_object(text: str) -> dict:
    text = text.strip()
    if not text:
        raise ValueError("empty router output")

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("json object not found")

    candidate = text[start : end + 1]
    return json.loads(candidate)
