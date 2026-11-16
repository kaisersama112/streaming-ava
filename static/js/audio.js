import { el } from "./dom.js";
import { state } from "./store.js";
import {
  LOCAL_BARGE_IN_COOLDOWN_MS,
  LOCAL_BARGE_IN_RELEASE_THRESHOLD,
  LOCAL_BARGE_IN_RMS_THRESHOLD,
  PLAYBACK_SAMPLE_RATE,
  STATIC_ASSET_VERSION,
  TARGET_SAMPLE_RATE,
} from "./config.js";
import { formatElapsed, setPill } from "./utils.js";
import { log } from "./log.js";
import { renderTimeline } from "./panels.js";

export function updateMicButton() {
  const btn = el("btnMic");
  if (!btn) return;
  if (state.isMicTransitioning) {
    btn.textContent = "启动中...";
    btn.disabled = true;
    btn.setAttribute("aria-busy", "true");
    setPill("micState", "启动中", "warn");
    return;
  }
  btn.textContent = state.isMicActive ? "关闭麦克风" : "开启麦克风";
  btn.classList.toggle("active", state.isMicActive);
  btn.disabled = false;
  btn.setAttribute("aria-busy", "false");
  btn.setAttribute("aria-pressed", state.isMicActive ? "true" : "false");
  setPill("micState", state.isMicActive ? "采集中" : "未开启", state.isMicActive ? "ok" : "muted");
}

export function updateMuteButton() {
  const btn = el("btnMute");
  if (!btn) return;
  btn.textContent = state.isMuted ? "取消静音" : "静音";
  btn.classList.toggle("active", state.isMuted);
  btn.setAttribute("aria-pressed", state.isMuted ? "true" : "false");
  setPill("muteState", state.isMuted ? "已静音" : "未静音", state.isMuted ? "warn" : "muted");
}

export function toggleMute() {
  state.isMuted = !state.isMuted;
  updateMuteButton();
  log(state.isMuted ? "麦克风已静音" : "麦克风已取消静音");
}

function setLevel(percent) {
  const bounded = Math.max(0, Math.min(100, percent));
  const fill = el("levelFill");
  if (fill) fill.style.width = `${bounded}%`;
  const value = el("levelValue");
  if (value) value.textContent = `${Math.round(bounded)}%`;
}

function stopLevelMeter() {
  if (state.levelAnimationId) {
    cancelAnimationFrame(state.levelAnimationId);
    state.levelAnimationId = null;
  }
  state.analyserNode = null;
  state.levelDataArray = null;
  setLevel(0);
}

function startLevelMeter() {
  if (!state.analyserNode || !state.levelDataArray) return;
  const tick = () => {
    if (!state.analyserNode || !state.levelDataArray) return;
    state.analyserNode.getByteTimeDomainData(state.levelDataArray);
    let sum = 0;
    for (let i = 0; i < state.levelDataArray.length; i += 1) {
      const normalized = (state.levelDataArray[i] - 128) / 128;
      sum += normalized * normalized;
    }
    setLevel(Math.min(100, Math.sqrt(sum / state.levelDataArray.length) * 220));
    state.levelAnimationId = requestAnimationFrame(tick);
  };
  tick();
}

export function resetCallTimer() {
  state.callStartedAt = null;
  state.callAccumulatedMs = 0;
  const timer = el("callTimer");
  if (timer) timer.textContent = "00:00";
}

function updateCallTimerDisplay() {
  const runningMs = state.callStartedAt ? Date.now() - state.callStartedAt : 0;
  const timer = el("callTimer");
  if (timer) timer.textContent = formatElapsed(state.callAccumulatedMs + runningMs);
}

function startCallTimer() {
  if (!state.callStartedAt) state.callStartedAt = Date.now();
  if (!state.timerIntervalId) {
    state.timerIntervalId = window.setInterval(updateCallTimerDisplay, 250);
  }
  updateCallTimerDisplay();
}

function stopCallTimer() {
  if (state.callStartedAt) {
    state.callAccumulatedMs += Date.now() - state.callStartedAt;
    state.callStartedAt = null;
  }
  if (state.timerIntervalId) {
    window.clearInterval(state.timerIntervalId);
    state.timerIntervalId = null;
  }
  updateCallTimerDisplay();
}

export async function ensurePlaybackContext() {
  if (!state.playbackCtx) {
    state.playbackCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: PLAYBACK_SAMPLE_RATE });
    state.playbackGainNode = state.playbackCtx.createGain();
    state.playbackGainNode.gain.value = 1.0;
    state.playbackGainNode.connect(state.playbackCtx.destination);
  }
  if (state.playbackCtx.state === "suspended") {
    await state.playbackCtx.resume();
  }
  state.playbackScheduledAt = Math.max(state.playbackScheduledAt, state.playbackCtx.currentTime);
  return state.playbackCtx;
}

export function stopPlaybackQueue() {
  for (const source of state.playbackSources) {
    try {
      source.stop();
    } catch {
      // 已结束的 source 重复 stop 会抛错，忽略
    }
  }
  state.playbackSources.clear();
  state.playbackScheduledAt = state.playbackCtx ? state.playbackCtx.currentTime : 0;
}

function estimatePcmRms(buf) {
  if (!buf || !buf.byteLength) return 0;
  const samples = new Int16Array(buf);
  if (!samples.length) return 0;
  let sum = 0;
  for (let i = 0; i < samples.length; i += 1) {
    const normalized = samples[i] / 32768;
    sum += normalized * normalized;
  }
  return Math.sqrt(sum / samples.length);
}

export function interruptPlayback(reason = "manual") {
  if (!state.ws || state.ws.readyState !== WebSocket.OPEN) {
    log("实时连接未建立，无法发送打断指令", "warn");
    return;
  }
  stopPlaybackQueue();
  state.ws.send(JSON.stringify({ type: "interrupt", reason }));
}

function maybeInterruptPlaybackFromMic(buf) {
  if (!state.ws || state.ws.readyState !== WebSocket.OPEN || state.isMuted) return;
  if (state.currentSessionState !== "speaking" && state.currentSessionState !== "thinking") {
    state.localSpeechInterruptArmed = true;
    return;
  }
  const rms = estimatePcmRms(buf);
  if (rms <= LOCAL_BARGE_IN_RELEASE_THRESHOLD) {
    state.localSpeechInterruptArmed = true;
    return;
  }
  if (rms < LOCAL_BARGE_IN_RMS_THRESHOLD) return;
  const now = Date.now();
  if (!state.localSpeechInterruptArmed || now - state.lastLocalInterruptAt < LOCAL_BARGE_IN_COOLDOWN_MS) return;
  state.localSpeechInterruptArmed = false;
  state.lastLocalInterruptAt = now;
  interruptPlayback("speech_start");
}

function decodeBase64ToInt16(base64) {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }
  return new Int16Array(bytes.buffer, bytes.byteOffset, Math.floor(bytes.byteLength / 2));
}

export async function playPcmChunk(base64, sampleRate) {
  if (!base64) return;
  const ctx = await ensurePlaybackContext();
  const samples = decodeBase64ToInt16(base64);
  if (!samples.length) return;

  const audioBuffer = ctx.createBuffer(1, samples.length, sampleRate || PLAYBACK_SAMPLE_RATE);
  const channel = audioBuffer.getChannelData(0);
  for (let i = 0; i < samples.length; i += 1) {
    channel[i] = samples[i] / 32768;
  }

  const source = ctx.createBufferSource();
  source.buffer = audioBuffer;
  source.connect(state.playbackGainNode);

  const startAt = Math.max(ctx.currentTime + 0.01, state.playbackScheduledAt || ctx.currentTime);
  const turnId = state.activeAssistantTurnId ? String(state.activeAssistantTurnId) : "";
  if (turnId && !state.playbackReportedTurns.has(turnId)) {
    state.playbackReportedTurns.add(turnId);
    const timeline = { ...state.lastTimeline };
    const basePushMs = Number(
      timeline.t7_first_push_pcm || timeline.t6_first_tts_chunk || timeline.t5_first_tts_submit || 0
    );
    timeline.t8_frontend_playback = Math.round(basePushMs + Math.max(0, startAt - ctx.currentTime) * 1000);
    renderTimeline(timeline);
    if (state.ws && state.ws.readyState === WebSocket.OPEN) {
      state.ws.send(
        JSON.stringify({
          type: "playback_started",
          turn_id: Number(turnId),
          timeline_ms: timeline,
          audio_context_time: ctx.currentTime,
        })
      );
    }
  }
  source.start(startAt);
  state.playbackScheduledAt = startAt + audioBuffer.duration;
  state.playbackSources.add(source);
  source.onended = () => state.playbackSources.delete(source);
}

export async function startMicrophone() {
  if (state.isMicActive) return;
  state.isMicTransitioning = true;
  updateMicButton();
  const { ensureConnected } = await import("./connection.js");
  await ensureConnected();
  await ensurePlaybackContext();

  state.mediaStream = await navigator.mediaDevices.getUserMedia({
    audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    video: false,
  });

  state.audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  await state.audioCtx.audioWorklet.addModule(`/static/audio-worklet.js?v=${STATIC_ASSET_VERSION}`);

  const source = state.audioCtx.createMediaStreamSource(state.mediaStream);
  state.analyserNode = state.audioCtx.createAnalyser();
  state.analyserNode.fftSize = 1024;
  state.levelDataArray = new Uint8Array(state.analyserNode.frequencyBinCount);

  state.workletNode = new AudioWorkletNode(state.audioCtx, "pcm-downsampler", {
    processorOptions: { targetSampleRate: TARGET_SAMPLE_RATE },
    numberOfInputs: 1,
    numberOfOutputs: 0,
    channelCount: 1,
  });

  state.workletNode.port.onmessage = (evt) => {
    if (!state.ws || state.ws.readyState !== WebSocket.OPEN || state.isMuted) return;
    const buf = evt.data;
    if (buf && buf.byteLength) {
      maybeInterruptPlaybackFromMic(buf);
      state.ws.send(buf);
    }
  };

  source.connect(state.analyserNode);
  source.connect(state.workletNode);
  startLevelMeter();
  startCallTimer();
  state.isMicActive = true;
  state.isMicTransitioning = false;
  updateMicButton();
  log(`麦克风已启动：音频上下文采样率=${state.audioCtx.sampleRate}`, "ok");
}

export async function stopMicrophone() {
  if (!state.audioCtx && !state.mediaStream && !state.workletNode) {
    state.isMicActive = false;
    updateMicButton();
    stopCallTimer();
    stopLevelMeter();
    return;
  }
  try {
    if (state.workletNode) {
      state.workletNode.port.onmessage = null;
      state.workletNode.disconnect();
      state.workletNode = null;
    }
    if (state.analyserNode) {
      state.analyserNode.disconnect();
      state.analyserNode = null;
    }
    if (state.audioCtx) {
      await state.audioCtx.close();
      state.audioCtx = null;
    }
    if (state.mediaStream) {
      state.mediaStream.getTracks().forEach((track) => track.stop());
      state.mediaStream = null;
    }
  } finally {
    state.isMicTransitioning = false;
    state.isMicActive = false;
    updateMicButton();
    stopCallTimer();
    stopLevelMeter();
    if (state.ws && state.ws.readyState === WebSocket.OPEN) {
      try {
        state.ws.send(JSON.stringify({ type: "mic_stopped" }));
      } catch (error) {
        log(`麦克风停止提交失败：${String(error?.message || error)}`, "warn");
      }
    }
    log("麦克风已停止");
  }
}

export async function toggleMicrophone() {
  if (state.isMicTransitioning) return;
  try {
    if (state.isMicActive) {
      await stopMicrophone();
    } else {
      await startMicrophone();
    }
  } catch (error) {
    log(`麦克风异常：${String(error?.message || error)}`, "error");
    await stopMicrophone();
  }
}