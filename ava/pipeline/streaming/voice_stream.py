"""低延迟流式 TTS 管线工具。

`StreamingVoicePipeline` 用于把文本流输入与具体 TTS 提供方解耦：
- 上游文本可以持续快速提交
- 后台线程负责分段、合并、送入语音合成
- 语音块结果再按流式方式向外消费
"""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass
from typing import Any

from ava.capabilities.tts import CosyVoiceSDKError, StreamingTTSClient, TTSError
from ava.capabilities.tts.factory import build_streaming_tts, normalize_tts_error


@dataclass(frozen=True)
class VoiceStreamConfig:
    """单个实时 TTS 推送器的通用配置。"""

    voice: Any
    audio_format: str = "pcm"
    sample_rate: int | None = None
    synth_segment_chars: int = 48
    synth_burst_chars: int = 96
    synth_feed_pause_seconds: float = 0.04
    synth_complete_timeout_millis: int = 15000


class StreamingVoicePipeline:
    """后台 TTS 推送器。

    它负责把文本 token 流与语音合成过程解耦，并尽量降低首包延迟。

    当前采用的刷新策略：
    1. 首次快速刷新：首批少量字符尽快送出
    2. 标点触发刷新：遇到句边界立即送出
    3. 时间触发刷新：持续输出时按短间隔推进
    4. 字符数触发刷新：缓冲达到阈值后送出
    """

    PUNCTUATION = set("。！？!?；;，、,\n")

    def __init__(self, config: VoiceStreamConfig) -> None:
        self._config = config
        # 上游文本流线程提交到这里。
        # `None` 作为结束哨兵，表示在缓冲内容送完后关闭后台推送线程。
        self._submit_queue: queue.Queue[str | None] = queue.Queue()
        self._done = threading.Event()
        self._interrupted = threading.Event()
        self._error: Exception | None = None
        # 这些统计会被实时指标读取，因此可变计数统一加锁保护。
        self._stats_lock = threading.Lock()
        self._submitted_items = 0
        self._submitted_chars = 0
        self._queued_chars = 0
        self._max_queue_depth = 0
        self._max_queued_chars = 0
        self._flushed_batches = 0
        self._flushed_chars = 0
        self._pending_buffer_chars = 0
        self._max_pending_buffer_chars = 0
        self._close_requested_at: float | None = None
        self._completed_at: float | None = None
        self._last_submit_at: float | None = None
        self._last_flush_at: float | None = None
        # 具体 TTS 提供方选择交给工厂层处理，
        # 这样实时流式链路不需要感知不同厂商的协议差异。
        self._synth = self._create_synth()
        self._flush_char_threshold = 8
        self._first_flush_char_threshold = 4
        self._flush_wait_seconds = 0.03
        self._first_flush_done = False
        self._synth_segment_chars = max(16, int(config.synth_segment_chars or 48))
        self._synth_burst_chars = max(self._synth_segment_chars, int(config.synth_burst_chars or 96))
        self._synth_feed_pause_seconds = max(0.0, float(config.synth_feed_pause_seconds or 0.0))
        self._synth_complete_timeout_millis = max(1000, int(config.synth_complete_timeout_millis or 15000))
        self._last_synth_feed_at: float | None = None
        self._synth_feed_calls = 0
        self._complete_timeout_count = 0
        self._last_complete_timeout_message: str = ""
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _create_synth(self) -> StreamingTTSClient:
        return build_streaming_tts(
            self._config.voice,
            audio_format=self._config.audio_format,
            sample_rate=self._config.sample_rate,
        )

    def submit(self, text: str) -> None:
        """提交文本片段，但不阻塞上游文本流生成。"""
        if self._interrupted.is_set() or self._done.is_set():
            return
        content = text.strip()
        if content:
            self._submit_queue.put(content)
            with self._stats_lock:
                self._submitted_items += 1
                self._submitted_chars += len(content)
                self._queued_chars += len(content)
                self._max_queue_depth = max(self._max_queue_depth, self._submit_queue.qsize())
                self._max_queued_chars = max(self._max_queued_chars, self._queued_chars)
                self._last_submit_at = time.monotonic()

    def interrupt(self) -> None:
        """尽快中断语音合成。

        用于全双工打断场景：
        - 停止继续送入新文本
        - 停止后台推送循环
        - 尽量减少尾部残留音频
        """
        if self._done.is_set():
            return
        self._interrupted.set()
        with self._stats_lock:
            self._close_requested_at = self._close_requested_at or time.monotonic()
        # 清空队列，避免中断后残留文本继续被送入 TTS。
        try:
            while True:
                queued = self._submit_queue.get_nowait()
                if isinstance(queued, str):
                    with self._stats_lock:
                        self._queued_chars = max(0, self._queued_chars - len(queued))
        except queue.Empty:
            pass
        # 尝试尽快结束底层合成，减少音频块继续产生。
        try:
            self._synth.complete(timeout_millis=1)
        except Exception:
            pass
        # 唤醒后台线程，避免阻塞等待。
        try:
            self._submit_queue.put_nowait(None)
        except Exception:
            pass

    def close(self) -> None:
        if self._done.is_set():
            return
        with self._stats_lock:
            self._close_requested_at = self._close_requested_at or time.monotonic()
        self._submit_queue.put(None)
        self._thread.join(timeout=5)

    def close_with_timeout(self, timeout_seconds: float = 30.0) -> bool:
        if self._done.is_set():
            return True
        with self._stats_lock:
            self._close_requested_at = self._close_requested_at or time.monotonic()
        self._submit_queue.put(None)
        self._thread.join(timeout=max(0.0, timeout_seconds))
        return not self._thread.is_alive()

    def wait_done(self, timeout_seconds: float | None = None) -> bool:
        return self._done.wait(timeout_seconds)

    @property
    def done(self) -> bool:
        return self._done.is_set()

    @property
    def error(self) -> Exception | None:
        return self._error

    def snapshot(self) -> dict[str, int | float | bool | None]:
        """返回当前推送器指标快照，供实时调试与追踪使用。"""
        with self._stats_lock:
            return {
                "submitted_items": self._submitted_items,
                "submitted_chars": self._submitted_chars,
                "queued_chars": self._queued_chars,
                "max_queue_depth": self._max_queue_depth,
                "max_queued_chars": self._max_queued_chars,
                "flushed_batches": self._flushed_batches,
                "flushed_chars": self._flushed_chars,
                "pending_buffer_chars": self._pending_buffer_chars,
                "max_pending_buffer_chars": self._max_pending_buffer_chars,
                "close_requested_at": self._close_requested_at,
                "completed_at": self._completed_at,
                "last_submit_at": self._last_submit_at,
                "last_flush_at": self._last_flush_at,
                "synth_feed_calls": self._synth_feed_calls,
                "complete_timeout_count": self._complete_timeout_count,
                "last_complete_timeout_message": self._last_complete_timeout_message,
                "done": self._done.is_set(),
                "interrupted": self._interrupted.is_set(),
                "error": bool(self._error),
            }

    def pop_chunks(self) -> list[bytes]:
        return self._synth.pop_chunks()

    def _has_punctuation(self, text: str) -> bool:
        return any(ch in self.PUNCTUATION for ch in text)

    def _should_flush(self, buffer: str) -> bool:
        if not buffer:
            return False

        stripped = buffer.strip()
        if not stripped:
            return False

        if not self._first_flush_done:
            if len(stripped) >= self._first_flush_char_threshold:
                return True
            if self._has_punctuation(stripped):
                return True
            return False

        if len(buffer) >= self._flush_char_threshold:
            return True

        if self._has_punctuation(stripped):
            return True

        return False

    def _split_for_synth(self, content: str) -> list[str]:
        content = content.strip()
        if not content:
            return []
        if len(content) <= self._synth_segment_chars:
            return [content]

        segments: list[str] = []
        current: list[str] = []
        last_boundary = -1
        min_boundary = max(12, self._synth_segment_chars // 2)

        for ch in content:
            current.append(ch)
            if ch in self.PUNCTUATION or ch in ":：)]）":
                last_boundary = len(current)
            if len(current) < self._synth_segment_chars:
                continue

            cut = last_boundary if last_boundary >= min_boundary else len(current)
            segment = "".join(current[:cut]).strip()
            if segment:
                segments.append(segment)
            current = current[cut:]
            last_boundary = -1
            for idx, cur_ch in enumerate(current, start=1):
                if cur_ch in self.PUNCTUATION or cur_ch in ":：)]）":
                    last_boundary = idx

        tail = "".join(current).strip()
        if tail:
            segments.append(tail)
        return segments

    def _feed_synth_segments(self, content: str) -> None:
        """Submit bounded segments to the provider to avoid large TTS bursts."""
        for segment in self._split_for_synth(content):
            if self._interrupted.is_set():
                return
            if self._last_synth_feed_at is not None and self._synth_feed_pause_seconds > 0.0:
                elapsed = time.monotonic() - self._last_synth_feed_at
                if elapsed < self._synth_feed_pause_seconds:
                    time.sleep(self._synth_feed_pause_seconds - elapsed)
            self._synth.feed(segment)
            self._last_synth_feed_at = time.monotonic()
            with self._stats_lock:
                self._synth_feed_calls += 1

    def _flush_buffer(self, buffer: str) -> str:
        content = buffer.strip()
        if content:
            self._feed_synth_segments(content)
            self._first_flush_done = True
            with self._stats_lock:
                self._flushed_batches += 1
                self._flushed_chars += len(content)
                self._last_flush_at = time.monotonic()
                self._pending_buffer_chars = 0
        return ""

    @staticmethod
    def _is_soft_complete_timeout(exc: Exception) -> bool:
        message = str(exc or "").strip().lower()
        return "wait for complete timeout" in message or "streaming_complete failed" in message and "timeout" in message

    def _complete_synth(self) -> None:
        try:
            self._synth.complete(timeout_millis=self._synth_complete_timeout_millis)
        except (CosyVoiceSDKError, TTSError) as exc:
            if not self._is_soft_complete_timeout(exc):
                raise
            with self._stats_lock:
                self._complete_timeout_count += 1
                self._last_complete_timeout_message = str(exc)

    def _run(self) -> None:
        """Background feeder loop that turns queued text into provider calls."""
        buffer = ""
        last_append_at = time.monotonic()

        try:
            while True:
                if self._interrupted.is_set():
                    break
                try:
                    item = self._submit_queue.get(timeout=0.02)
                except queue.Empty:
                    item = "__timeout__"

                now = time.monotonic()
                if item == "__timeout__":
                    if buffer:
                        elapsed = now - last_append_at
                        if self._has_punctuation(buffer) and elapsed >= 0.01:
                            buffer = self._flush_buffer(buffer)
                        elif elapsed >= self._flush_wait_seconds:
                            if self._should_flush(buffer):
                                buffer = self._flush_buffer(buffer)
                    continue

                if item is None:
                    if buffer.strip():
                        self._flush_buffer(buffer)
                    self._complete_synth()
                    break

                # Keep a moderate local backlog, but do not shovel the entire LLM burst
                # into the provider at once. Long replies are expected to outpace speech.
                burst_parts = [item]
                burst_chars = len(item)
                close_requested = False
                while burst_chars < self._synth_burst_chars:
                    try:
                        queued = self._submit_queue.get_nowait()
                    except queue.Empty:
                        break
                    if queued is None:
                        close_requested = True
                        break
                    burst_chars += len(queued)
                    burst_parts.append(queued)

                buffer += "".join(burst_parts)
                last_append_at = now
                with self._stats_lock:
                    self._queued_chars = max(0, self._queued_chars - burst_chars)
                    self._pending_buffer_chars = len(buffer)
                    self._max_pending_buffer_chars = max(self._max_pending_buffer_chars, len(buffer))

                if close_requested:
                    if buffer.strip():
                        buffer = self._flush_buffer(buffer)
                    self._complete_synth()
                    break

                if self._has_punctuation(buffer):
                    buffer = self._flush_buffer(buffer)
                elif self._should_flush(buffer):
                    buffer = self._flush_buffer(buffer)
        except Exception as exc:
            self._error = normalize_tts_error(exc)
        finally:
            with self._stats_lock:
                self._completed_at = time.monotonic()
                self._pending_buffer_chars = 0
            self._done.set()


