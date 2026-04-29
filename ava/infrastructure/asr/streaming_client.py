"""Session-friendly streaming ASR wrapper.

The underlying DashScope SDK uses callbacks. For full-duplex orchestration we
prefer a pull-based interface that can be stopped and drained deterministically.
"""

from __future__ import annotations

from collections import deque
import queue
import threading
import time
from dataclasses import dataclass

from .streaming_sdk import ASRConfig, ASRError, StreamingASR


@dataclass(frozen=True)
class ASRResult:
    text: str
    is_final: bool
    received_at: float
    stability: float | None = None
    start_ms: int | None = None
    end_ms: int | None = None


class StreamingASRClient:
    """Callback-to-queue adapter for StreamingASR.

    Typical usage (pseudo):
      client = StreamingASRClient(cfg)
      client.start()
      client.send_audio(frame)
      for result in client.iter_results(timeout=0.2):
          ...
      client.stop()
    """

    def __init__(self, config: ASRConfig, max_queue_size: int = 256, max_pending_chunks: int = 20) -> None:
        self.config = config
        self._asr = StreamingASR(config)
        self._queue: queue.Queue[ASRResult] = queue.Queue(maxsize=max_queue_size)
        self._pending_audio: deque[bytes] = deque(maxlen=max_pending_chunks)
        self._started = False
        self._stopped = threading.Event()
        self._lock = threading.RLock()
        self._error: Exception | None = None
        self._pending_flush_thread: threading.Thread | None = None

    @property
    def error(self) -> Exception | None:
        return self._error

    @property
    def stopped(self) -> bool:
        return self._stopped.is_set()

    @staticmethod
    def is_recoverable_error(exc: Exception) -> bool:
        text = str(exc).lower()
        return any(
            marker in text
            for marker in (
                "connection closed",
                "idle timeout",
                "broken pipe",
                "connection reset",
            )
        )

    def _on_text(self, text: str, is_final: bool, metadata: dict | None = None) -> None:
        if self._stopped.is_set():
            return
        try:
            # Best-effort: drop if the consumer is slow.
            metadata = metadata or {}
            item = ASRResult(
                text=text or "",
                is_final=bool(is_final),
                received_at=time.monotonic(),
                stability=metadata.get("stability"),
                start_ms=metadata.get("start_ms"),
                end_ms=metadata.get("end_ms"),
            )
            try:
                self._queue.put_nowait(item)
            except queue.Full:
                # Drop oldest then enqueue newest (keeps stream "fresh").
                try:
                    _ = self._queue.get_nowait()
                except Exception:
                    pass
                try:
                    self._queue.put_nowait(item)
                except Exception:
                    pass
        except Exception as exc:
            self._error = exc
            self._stopped.set()

    def _enqueue_pending_audio(self, audio_data: bytes) -> None:
        if audio_data:
            self._pending_audio.append(bytes(audio_data))

    def _drain_pending_audio(self) -> list[bytes]:
        pending = list(self._pending_audio)
        self._pending_audio.clear()
        return pending

    def _requeue_pending_audio(self, audio_chunks: list[bytes]) -> None:
        for chunk in reversed(audio_chunks):
            try:
                self._pending_audio.appendleft(chunk)
            except Exception:
                break

    def _ensure_pending_flush_thread(self) -> None:
        with self._lock:
            thread = self._pending_flush_thread
            if thread is not None and thread.is_alive():
                return
            thread = threading.Thread(target=self._flush_pending_when_ready, daemon=True)
            self._pending_flush_thread = thread
            thread.start()

    def _flush_pending_when_ready(self) -> None:
        deadline = time.monotonic() + 5.0
        while not self._stopped.is_set() and time.monotonic() < deadline:
            with self._lock:
                asr = self._asr
                ready = asr.ready
                has_pending = bool(self._pending_audio)
                if ready and has_pending:
                    pending = self._drain_pending_audio()
                else:
                    pending = []

            if not has_pending:
                return

            if not ready:
                time.sleep(0.02)
                continue

            try:
                for chunk in pending:
                    asr.send_audio(chunk)
            except Exception as exc:
                with self._lock:
                    self._error = exc
                    self._requeue_pending_audio(pending)
                return

            time.sleep(0.005)

    def start(self) -> None:
        with self._lock:
            if self._started and not self._stopped.is_set():
                return
            self._stopped.clear()
            self._error = None
            self._started = True

        try:
            self._asr.start(self._on_text)
            self._ensure_pending_flush_thread()
        except Exception as exc:
            self._error = exc
            self._stopped.set()
            raise

    def send_audio(self, audio_data: bytes) -> None:
        if self._stopped.is_set():
            return
        with self._lock:
            asr = self._asr
            if not asr.ready:
                self._enqueue_pending_audio(audio_data)
                self._ensure_pending_flush_thread()
                return
            pending = self._drain_pending_audio()
        try:
            for chunk in pending:
                asr.send_audio(chunk)
            asr.send_audio(audio_data)
        except Exception as exc:
            with self._lock:
                self._requeue_pending_audio(pending)
                self._enqueue_pending_audio(audio_data)
            self._error = exc
            raise

    def restart(self) -> None:
        with self._lock:
            previous_asr = self._asr
            self._asr = StreamingASR(self.config)
            self._started = False
            self._stopped.clear()
            self._error = None
        try:
            previous_asr.stop()
        except Exception:
            pass
        self.start()

    def commit(self) -> None:
        if self._stopped.is_set():
            return
        with self._lock:
            asr = self._asr
            pending = self._drain_pending_audio()
        try:
            for chunk in pending:
                asr.send_audio(chunk)
            asr.commit()
        except Exception as exc:
            with self._lock:
                self._requeue_pending_audio(pending)
            self._error = exc
            raise

    def iter_results(self, timeout: float = 0.1):
        """Yield ASRResult items until stopped.

        This is a non-blocking-ish iterator: it returns control at least every
        `timeout` seconds so callers can interleave other work.
        """
        while not self._stopped.is_set():
            if self._error is not None:
                raise ASRError(str(self._error))
            try:
                item = self._queue.get(timeout=timeout)
            except queue.Empty:
                yield from ()
                continue
            yield item

    def pop_results(self, max_items: int = 32) -> list[ASRResult]:
        out: list[ASRResult] = []
        for _ in range(max_items):
            try:
                out.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return out

    def stop(self) -> None:
        if self._stopped.is_set():
            return
        self._stopped.set()
        try:
            self._asr.stop()
        except Exception:
            # best-effort stop
            pass
