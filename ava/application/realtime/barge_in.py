"""Barge-in decision policy for full-duplex sessions."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class BargeInConfig:
    min_partial_chars: int = 2
    stability_threshold: float = 0.35
    cooldown_ms: int = 450


class BargeInDetector:
    def __init__(self, config: BargeInConfig | None = None) -> None:
        self.config = config or BargeInConfig()
        self._lock = threading.Lock()
        self._last_interrupt_at = 0.0

    def should_interrupt(
        self,
        text: str,
        stability: float | None = None,
        *,
        is_speaking: bool,
        now: float | None = None,
    ) -> bool:
        if not is_speaking:
            return False

        stripped = (text or "").strip()
        if len(stripped) < self.config.min_partial_chars:
            return False

        if stability is not None and stability < self.config.stability_threshold:
            return False

        moment = time.monotonic() if now is None else now
        with self._lock:
            cooldown = self.config.cooldown_ms / 1000.0
            if (moment - self._last_interrupt_at) < cooldown:
                return False
            self._last_interrupt_at = moment
            return True
