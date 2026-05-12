"""Queue-backed bridge between TTS PCM chunks and FastRTC playback."""

from __future__ import annotations

import atexit
import logging
import queue
import threading
from dataclasses import dataclass

import numpy as np

from ava.interfaces.websocket.audio_patch import patch_fastrtc_player_decode

_LOG = logging.getLogger("streaming_ava.realtime")


@dataclass
class PlayerConfig:
    host: str = "127.0.0.1"
    port: int = 7860
    public_url: str = ""
    sample_rate: int = 24000


class RealtimeAudioBridge:
    def __init__(self, config: PlayerConfig):
        self.config = config
        # Do not aggressively bound the queue or drop chunks: streaming TTS tail audio
        # is often generated after the UI finishes token streaming, and dropping/truncating
        # creates audible "swallowed words".
        self._queue: queue.Queue[tuple[int, np.ndarray] | None] = queue.Queue()
        self._lock = threading.Lock()
        self._launched = False
        self._closed = False
        self._url = ""
        self._stream = None
        self._handler_fn = None

    def _handler(self):
        try:
            from fastrtc.utils import CloseStream
        except ImportError:
            CloseStream = None

        try:
            while True:
                item = self._queue.get()
                if item is None:
                    # Notify FastRTC that the stream is closing, then exit.
                    if CloseStream is not None:
                        yield CloseStream()
                    _LOG.info("RealtimeAudioBridge handler received close sentinel.")
                    break
                yield item
        except Exception:
            # 忽略handler中的异常，确保连接能够正常关闭
            _LOG.exception("RealtimeAudioBridge handler crashed unexpectedly.")

    def launch(self) -> str:
        with self._lock:
            if self._closed:
                raise RuntimeError("RealtimeAudioBridge is already closed")
            if self._launched:
                return self._url

            try:
                from fastrtc import Stream
            except ImportError as exc:  # pragma: no cover
                raise RuntimeError(
                    "fastrtc is not installed. Run: pip install 'fastrtc>=0.0.34,<0.0.35'"
                ) from exc

            patch_fastrtc_player_decode()

            # FastRTC sets attributes on the handler callable.
            # Bound methods do not allow arbitrary attribute assignment.
            def handler():
                yield from self._handler()

            self._handler_fn = handler
            self._stream = Stream(
                handler=self._handler_fn,
                mode="receive",
                modality="audio",
                ui_args={
                    "hide_title": True,
                    "variant": "wave",
                },
            )
            self._stream.ui.launch(
                server_name=self.config.host,
                server_port=self.config.port,
                prevent_thread_lock=True,
                quiet=True,
                share=False,
            )
            self._url = self.config.public_url or f"http://127.0.0.1:{self.config.port}"
            self._launched = True
            _LOG.info("RealtimeAudioBridge launched at %s (sr=%s).", self._url, self.config.sample_rate)
            return self._url

    def stop_current_stream(self) -> None:
        """Request the current FastRTC receive stream to close.

        This is best-effort: FastRTC runs its own server loop and the UI may keep
        serving a page, but the underlying generator should receive a CloseStream
        and terminate.
        """
        with self._lock:
            if self._closed or not self._launched:
                return
            try:
                # Signal the handler generator to close.
                self._queue.put_nowait(None)
            except Exception:
                _LOG.exception("Failed to enqueue close sentinel for stop_current_stream().")
            # Allow relaunch to create a new handler stream.
            self._launched = False

    def new_stream(self) -> str:
        """Start a fresh receive stream after an interrupt.

        Useful when flushing the queue is not enough due to receiver-side jitter
        buffers: recreating the stream reduces residual tail playback.
        """
        with self._lock:
            if self._closed:
                raise RuntimeError("RealtimeAudioBridge is already closed")
            # Close existing handler and drop queued audio.
            try:
                self.flush()
            except Exception:
                pass
            try:
                self._queue.put_nowait(None)
            except Exception:
                pass
            # Replace the queue so a new handler won't see old sentinels/frames.
            self._queue = queue.Queue()
            self._launched = False
        return self.launch()

    def push_pcm_bytes(self, chunk: bytes) -> None:
        if self._closed:
            _LOG.warning("push_pcm_bytes ignored: bridge already closed.")
            return
        if not chunk:
            return
        try:
            if (len(chunk) % 2) != 0:
                _LOG.warning("push_pcm_bytes got odd-length PCM bytes: %s", len(chunk))
                chunk = chunk[:-1]
            if not chunk:
                return
            arr = np.frombuffer(chunk, dtype=np.int16)
            if arr.size == 0:
                return
            # Block-free queue by default; avoid dropping audio chunks.
            self._queue.put((self.config.sample_rate, arr))
        except Exception:
            # 忽略处理音频数据时的异常
            _LOG.exception("push_pcm_bytes failed (len=%s).", len(chunk))

    def flush(self) -> None:
        """Drop all queued (not-yet-played) audio frames.

        Used for full-duplex barge-in to stop playback as fast as possible.
        Note: already-sent WebRTC frames cannot be retracted; this only clears
        the local queue.
        """
        if self._closed:
            return
        dropped = 0
        try:
            while True:
                item = self._queue.get_nowait()
                if item is None:
                    # Keep the close sentinel if it was already enqueued.
                    self._queue.put_nowait(None)
                    break
                dropped += 1
        except queue.Empty:
            pass
        except Exception:
            _LOG.exception("RealtimeAudioBridge.flush failed.")
        if dropped:
            _LOG.info("RealtimeAudioBridge.flush dropped %s queued frames.", dropped)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._launched = False
            # Signal the handler to gracefully drain and then close.
            try:
                self._queue.put_nowait(None)
            except Exception:
                _LOG.exception("Failed to enqueue close sentinel for handler.")
            # 清理stream
            self._stream = None
            _LOG.info("RealtimeAudioBridge closed.")


_BRIDGE: RealtimeAudioBridge | None = None


def get_bridge(config: PlayerConfig) -> RealtimeAudioBridge:
    global _BRIDGE
    if _BRIDGE is None:
        _BRIDGE = RealtimeAudioBridge(config)
        return _BRIDGE

    current = _BRIDGE.config
    if (
        current.host != config.host
        or current.port != config.port
        or current.public_url != config.public_url
        or current.sample_rate != config.sample_rate
    ):
        try:
            _BRIDGE.close()
        except Exception:
            _LOG.exception("Failed to close existing RealtimeAudioBridge before reconfigure.")
        _BRIDGE = RealtimeAudioBridge(config)
    return _BRIDGE


def stop_bridge() -> None:
    global _BRIDGE
    if _BRIDGE is not None:
        _BRIDGE.close()


atexit.register(stop_bridge)
