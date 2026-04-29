"""FastRTC compatibility patch for graceful shutdown and stable playback."""

from __future__ import annotations

import asyncio
import fractions
import logging

import numpy as np


def patch_fastrtc_player_decode() -> None:
    import fastrtc.utils as u

    if getattr(u, "_streaming_ava_patched", False):
        return

    async def patched_player_worker_decode(
        next_frame,
        queue,
        thread_quit,
        channel,
        set_additional_outputs,
        quit_on_none: bool = False,
        sample_rate: int = 48000,
        frame_size: int = int(48000 * u.AUDIO_PTIME),
    ):
        audio_samples = 0
        audio_time_base = fractions.Fraction(1, sample_rate)
        audio_resampler = u.av.AudioResampler(
            format="s16",
            layout="stereo",
            rate=sample_rate,
            frame_size=frame_size,
        )
        first_sample_rate = None

        while not thread_quit.is_set():
            try:
                frame, outputs = u.split_output(await asyncio.wait_for(next_frame(), timeout=60))
                if (
                    isinstance(outputs, u.AdditionalOutputs)
                    and set_additional_outputs
                    and channel
                    and channel()
                ):
                    set_additional_outputs(outputs)
                    channel().send(u.create_message("fetch_output", []))

                if frame is None:
                    if isinstance(outputs, u.CloseStream):
                        await queue.put(outputs)
                    if quit_on_none:
                        await queue.put(None)
                        break
                    continue

                if not isinstance(frame, tuple) or not isinstance(frame[1], np.ndarray):
                    raise u.WebRTCError(
                        "The frame must be a tuple containing a sample rate and a numpy array."
                    )

                if len(frame) == 2:
                    sr, audio_array = frame
                    layout = "mono"
                elif len(frame) == 3:
                    sr, audio_array, layout = frame
                else:
                    raise ValueError(f"frame must be of length 2 or 3, got: {len(frame)}")

                format_ = "s16" if audio_array.dtype == "int16" else "fltp"
                if first_sample_rate is None:
                    first_sample_rate = sr
                if format_ == "s16":
                    audio_array = u.audio_to_float32(audio_array)
                if first_sample_rate != sr:
                    audio_array = u.librosa.resample(
                        audio_array, target_sr=first_sample_rate, orig_sr=sr
                    )
                if audio_array.ndim == 1:
                    audio_array = audio_array.reshape(1, -1)

                aframe = u.av.AudioFrame.from_ndarray(
                    audio_array,
                    format="fltp",
                    layout=layout,
                )
                aframe.sample_rate = first_sample_rate
                for processed_frame in audio_resampler.resample(aframe):
                    processed_frame.pts = audio_samples
                    processed_frame.time_base = audio_time_base
                    audio_samples += processed_frame.samples
                    await queue.put(processed_frame)

                if isinstance(outputs, u.CloseStream):
                    await queue.put(outputs)
            except (TimeoutError, asyncio.TimeoutError):
                continue
            except Exception as exc:  # pragma: no cover
                msg = str(exc)
                if "cannot schedule new futures after shutdown" in msg or "Event loop is closed" in msg:
                    try:
                        await queue.put(None)
                    except Exception:
                        pass
                    break
                if "Received ICE candidate for unknown connection" in msg:
                    # 忽略已关闭连接的ICE候选消息
                    continue
                if isinstance(exc, u.WebRTCError):
                    raise exc
                continue

    u.player_worker_decode = patched_player_worker_decode
    u.logger.setLevel(logging.CRITICAL)
    u._streaming_ava_patched = True
