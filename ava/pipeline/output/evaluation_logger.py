"""Append-only JSONL evaluation logger for strategy tuning."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from configs import BASE_DIR


def _resolve_path(path_str: str) -> Path:
    path = Path(path_str)
    if path.is_absolute():
        return path
    return BASE_DIR / path


def append_evaluation_log(log_file: str, payload: dict[str, Any]) -> None:
    path = _resolve_path(log_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        **payload,
        "logged_at": datetime.now().isoformat(timespec="seconds"),
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
