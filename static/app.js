const el = (id) => document.getElementById(id);

const logEl = el("log");
const connStateEl = el("connState");
const sessionIdInputEl = el("sessionId");
const currentSessionIdEl = el("currentSessionId");
const micStateEl = el("micState");
const sessionStateEl = el("sessionState");
const speakerStateEl = el("speakerState");
const speakerStateMirrorEl = el("speakerStateMirror");
const callTimerEl = el("callTimer");
const muteStateEl = el("muteState");
const levelFillEl = el("levelFill");
const levelValueEl = el("levelValue");
const wsUrlEl = el("wsUrl");
const audioSpecEl = el("audioSpec");
const playerUrlEl = el("playerUrl");
const playerFrameEl = el("playerFrame");
const partialEl = el("partial");
const finalEl = el("final");
const transcriptEl = el("transcript");
const textInputEl = el("textInput");
const attachmentInputEl = el("attachmentInput");
const attachmentUrlInputEl = el("attachmentUrlInput");
const attachmentListEl = el("attachmentList");
const stagedAttachmentStateEl = el("stagedAttachmentState");
const currentRouteEl = el("currentRoute");
const currentHandlerEl = el("currentHandler");
const currentBranchEl = el("currentBranch");
const currentStrategyEl = el("currentStrategy");
const currentStrategyNameEl = el("currentStrategyName");
const currentDeliveryEl = el("currentDelivery");
const currentUiModeEl = el("currentUiMode");
const currentFollowupTypeEl = el("currentFollowupType");
const currentRenderTemplateEl = el("currentRenderTemplate");
const currentStrategySourceEl = el("currentStrategySource");
const currentArtifactSubjectHintEl = el("currentArtifactSubjectHint");
const currentArtifactTaskHintEl = el("currentArtifactTaskHint");
const multimodalSummaryEl = el("multimodalSummary");
const artifactTextViewEl = el("artifactTextView");
const memorySummaryEl = el("memorySummary");
const historySummaryEl = el("historySummary");
const factsViewEl = el("factsView");
const promptViewEl = el("promptView");
const timelineViewEl = el("timelineView");
const metricAsrFinalLatencyEl = el("metricAsrFinalLatency");
const metricFirstTokenLatencyEl = el("metricFirstTokenLatency");
const metricFirstAudioLatencyEl = el("metricFirstAudioLatency");
const metricInterruptCountEl = el("metricInterruptCount");

const btnConnect = el("btnConnect");
const btnMic = el("btnMic");
const btnMute = el("btnMute");
const btnInterrupt = el("btnInterrupt");
const btnClear = el("btnClear");
const btnSend = el("btnSend");
const btnApplySession = el("btnApplySession");
const btnPickAttachment = el("btnPickAttachment");
const btnAddAttachmentUrl = el("btnAddAttachmentUrl");
const btnClearAttachment = el("btnClearAttachment");
const btnCopyStrategyContext = el("btnCopyStrategyContext");

const TARGET_SAMPLE_RATE = 16000;
const MAX_LOG_CHARS = 12000;
const SESSION_STORAGE_KEY = "ava.realtime.session_id";

let ws = null;
let connectPromise = null;
let audioCtx = null;
let mediaStream = null;
let workletNode = null;
let analyserNode = null;
let levelDataArray = null;
let levelAnimationId = null;
let timerIntervalId = null;
let playbackCtx = null;
let playbackGainNode = null;
let playbackScheduledAt = 0;
let playbackSources = new Set();
const playbackReportedTurns = new Set();
let isMicActive = false;
let isMuted = false;
let callStartedAt = null;
let callAccumulatedMs = 0;
let activeAssistantTurnId = null;
let partialDraftId = null;
let pendingAttachments = [];
const interruptedAssistantTurns = new Set();

const assistantNodes = new Map();
const userMessageKeys = new Set();
const messageMetaStore = new Map();
let localMessageSeq = 0;

function normalizeSessionId(value) {
  const normalized = String(value || "")
    .trim()
    .replace(/[^\w\-.:]/g, "_")
    .slice(0, 64);
  return normalized || "default";
}

function getDesiredSessionId() {
  return normalizeSessionId(sessionIdInputEl?.value || localStorage.getItem(SESSION_STORAGE_KEY) || "default");
}

function applySessionId(value, { persist = true, reflectCurrent = false } = {}) {
  const normalized = normalizeSessionId(value);
  if (sessionIdInputEl) {
    sessionIdInputEl.value = normalized;
  }
  if (persist) {
    localStorage.setItem(SESSION_STORAGE_KEY, normalized);
  }
  if (reflectCurrent && currentSessionIdEl) {
    setCodeText(currentSessionIdEl, normalized);
  }
  if (wsUrlEl) {
    wsUrlEl.textContent = buildWsUrl();
  }
  return normalized;
}

function buildWsUrl() {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  const url = new URL(`${proto}//${location.host}/ws/audio`);
  url.searchParams.set("session_id", getDesiredSessionId());
  return url.toString();
}

function log(line) {
  const ts = new Date().toISOString().slice(11, 19);
  const next = `[${ts}] ${line}\n${logEl.textContent}`;
  logEl.textContent = next.slice(0, MAX_LOG_CHARS);
}

function setPillValue(target, text, className = "muted") {
  target.textContent = text;
  target.className = `pill-value ${className}`;
}

function setSpeakerState(text, className = "muted") {
  setPillValue(speakerStateEl, text, className);
  if (speakerStateMirrorEl) {
    setPillValue(speakerStateMirrorEl, text, className);
  }
}

function setLiveText(target, text, fallback) {
  target.textContent = text && String(text).trim() ? String(text).trim() : fallback;
}

function setCodeText(target, text, fallback = "-") {
  target.textContent = text && String(text).trim() ? String(text).trim() : fallback;
}

function formatLatency(value) {
  if (!Number.isFinite(Number(value))) return "-";
  const ms = Number(value);
  if (ms >= 1000) return `${(ms / 1000).toFixed(2)}s`;
  return `${Math.round(ms)}ms`;
}

function setMetricValue(target, value, formatter = formatLatency) {
  if (!target) return;
  target.textContent = formatter(value);
}

function formatTimelineMap(timeline = {}) {
  const labels = [
    ["t0_submit", "t0 用户提交"],
    ["t1_prepare_state_done", "t1 prepare_state_for_turn 完成"],
    ["t2_router_done", "t2 router.route 完成"],
    ["t3_turn_plan_done", "t3 build_turn_plan 完成"],
    ["t4_first_token", "t4 第一个 token"],
    ["t5_first_tts_submit", "t5 第一次 submit 到 TTS"],
    ["t6_first_tts_chunk", "t6 第一个 chunk 可用"],
    ["t7_first_push_pcm", "t7 第一次 push_pcm_bytes"],
    ["t8_frontend_playback", "t8 前端开始播放"],
  ];
  return labels
    .map(([key, label]) => {
      const value = timeline[key];
      return `${label}: ${Number.isFinite(Number(value)) ? `${Math.round(Number(value))}ms` : "-"}`;
    })
    .join("\n");
}

function scrollTranscriptToBottom() {
  transcriptEl.scrollTop = transcriptEl.scrollHeight;
}

function formatBytes(bytes) {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let idx = 0;
  while (value >= 1024 && idx < units.length - 1) {
    value /= 1024;
    idx += 1;
  }
  return `${value.toFixed(value >= 10 || idx === 0 ? 0 : 1)} ${units[idx]}`;
}

function describeAttachment(file) {
  if ((file.mime_type || "").startsWith("image/")) return "图片";
  if ((file.mime_type || "").startsWith("audio/")) return "音频";
  if ((file.mime_type || "").startsWith("video/")) return "视频";
  return "文件";
}

function attachmentSummary(attachments = []) {
  if (!attachments.length) return "";
  return attachments.map((item) => `[${describeAttachment(item)}] ${item.name}`).join("\n");
}

function compactValue(value, fallback = "-") {
  return value && String(value).trim() ? String(value).trim() : fallback;
}

function getAttachmentPreviewSource(item) {
  const candidate = item.preview_url || item.data_url || item.uri || "";
  return typeof candidate === "string" ? candidate : "";
}

function appendAttachmentPreviews(container, attachments = []) {
  for (const item of attachments) {
    const src = getAttachmentPreviewSource(item);
    if (!src) continue;

    const mimeType = String(item.mime_type || "");
    const preview = document.createElement("div");
    preview.className = "attachment-preview";

    if (mimeType.startsWith("image/")) {
      const img = document.createElement("img");
      img.src = src;
      img.alt = item.name || "image";
      preview.appendChild(img);
    } else if (mimeType.startsWith("audio/")) {
      const audio = document.createElement("audio");
      audio.controls = true;
      audio.preload = "metadata";
      audio.src = src;
      preview.appendChild(audio);
    } else if (mimeType.startsWith("video/")) {
      const video = document.createElement("video");
      video.controls = true;
      video.preload = "metadata";
      video.src = src;
      preview.appendChild(video);
    } else {
      continue;
    }

    container.appendChild(preview);
  }
}

function updateAttachmentState() {
  if (!stagedAttachmentStateEl) return;
  if (!pendingAttachments.length) {
    stagedAttachmentStateEl.textContent = "未选择附件。上传后，这批文件会固定挂载在当前会话上，直到你手动移除。";
    return;
  }
  const isOpen = !!ws && ws.readyState === WebSocket.OPEN;
  stagedAttachmentStateEl.textContent = isOpen
    ? `已选择 ${pendingAttachments.length} 个附件，并已同步到当前会话。后续文本发送和语音提问都会持续带上它们，直到手动移除。`
    : `已选择 ${pendingAttachments.length} 个附件，当前仅保存在本地。建立连接后会自动同步到会话。`;
}

function renderMessageMeta(container, meta = {}) {
  if (!container) return;
  container.innerHTML = "";
  const items = [
    ["branch", meta.branch],
    ["strategy", meta.strategy_id],
    ["name", meta.strategy_name],
    ["mode", meta.delivery_mode],
    ["ui", meta.ui_mode],
    ["follow-up", meta.user_followup_type],
    ["template", meta.render_template],
    ["source", meta.strategy_source],
  ];
  for (const [label, value] of items) {
    if (!value || !String(value).trim()) continue;
    const chip = document.createElement("span");
    chip.className = "message-chip";
    chip.innerHTML = `<strong>${label}</strong><span>${String(value).trim()}</span>`;
    container.appendChild(chip);
  }
}

function createMessageNode(role, key, text = "", attachments = [], meta = null) {
  const article = document.createElement("article");
  article.className = `message ${role}`;
  article.dataset.key = key;

  const roleEl = document.createElement("div");
  roleEl.className = "message-role";
  roleEl.textContent = role === "user" ? "User" : role === "assistant" ? "AVA" : "System";
  article.appendChild(roleEl);

  if (attachments.length) {
    const attachmentBlock = document.createElement("div");
    attachmentBlock.className = "message-text";
    attachmentBlock.textContent = attachmentSummary(attachments);
    article.appendChild(attachmentBlock);
    appendAttachmentPreviews(article, attachments);
  }

  const textEl = document.createElement("div");
  textEl.className = "message-text";
  textEl.textContent = text;
  article.appendChild(textEl);

  const metaEl = document.createElement("div");
  metaEl.className = "message-meta";
  article.appendChild(metaEl);
  if (meta) {
    messageMetaStore.set(key, { ...(messageMetaStore.get(key) || {}), ...meta });
    renderMessageMeta(metaEl, messageMetaStore.get(key));
  }

  transcriptEl.appendChild(article);
  scrollTranscriptToBottom();
  return article;
}

function getMessageTextEl(node) {
  if (!node) return null;
  const blocks = node.querySelectorAll(".message-text");
  return blocks.length ? blocks[blocks.length - 1] : null;
}

function addMessage(role, text, options = {}) {
  const key = options.key || `${role}-${Date.now()}-${localMessageSeq++}`;
  if (role === "user") {
    if (userMessageKeys.has(key)) {
      return key;
    }
    userMessageKeys.add(key);
  }
  const node = createMessageNode(role, key, text, options.attachments || [], options.meta || null);
  if (options.interrupted) {
    node.classList.add("interrupted");
  }
  if (role === "assistant") {
    assistantNodes.set(key, node);
  }
  return key;
}

function ensureAssistantMessage(turnId) {
  const key = String(turnId || `assistant-${Date.now()}`);
  let node = assistantNodes.get(key);
  if (!node) {
    node = createMessageNode("assistant", key, "", [], messageMetaStore.get(key) || null);
    assistantNodes.set(key, node);
  }
  activeAssistantTurnId = key;
  return node;
}

function setMessageMeta(key, patch = {}) {
  const normalizedKey = String(key || "");
  if (!normalizedKey) return;
  const merged = { ...(messageMetaStore.get(normalizedKey) || {}), ...patch };
  messageMetaStore.set(normalizedKey, merged);
  const node = transcriptEl.querySelector(`[data-key="${normalizedKey}"]`);
  if (!node) return;
  const metaEl = node.querySelector(".message-meta");
  renderMessageMeta(metaEl, merged);
}

function appendAssistantToken(turnId, token) {
  const node = ensureAssistantMessage(turnId);
  const textEl = getMessageTextEl(node);
  if (!textEl) return;
  textEl.textContent += token || "";
  scrollTranscriptToBottom();
}

function finishAssistant(turnId, interrupted = false, text = "") {
  const key = String(turnId || activeAssistantTurnId || "");
  if (!key) return;
  const node = ensureAssistantMessage(key);
  const textEl = getMessageTextEl(node);
  if (textEl && !textEl.textContent && text) {
    textEl.textContent = text;
  }
  if (interrupted) {
    node.classList.add("interrupted");
  }
  activeAssistantTurnId = null;
  setSpeakerState(interrupted ? "已打断" : "回复完成", interrupted ? "warn" : "ok");
}

function upsertPartialDraft(text) {
  const clean = (text || "").trim();
  if (!clean) {
    flushPartialDraft();
    return;
  }
  if (!partialDraftId) {
    partialDraftId = addMessage("user", clean, { key: "partial-draft" });
  } else {
    const node = transcriptEl.querySelector(`[data-key="${partialDraftId}"]`);
    if (node) {
      const textEl = getMessageTextEl(node);
      if (textEl) textEl.textContent = clean;
    }
  }
  scrollTranscriptToBottom();
}

function flushPartialDraft() {
  if (!partialDraftId) return;
  const node = transcriptEl.querySelector(`[data-key="${partialDraftId}"]`);
  if (node) node.remove();
  partialDraftId = null;
}

function clearTranscript() {
  assistantNodes.clear();
  userMessageKeys.clear();
  messageMetaStore.clear();
  interruptedAssistantTurns.clear();
  activeAssistantTurnId = null;
  partialDraftId = null;
  transcriptEl.innerHTML = "";
}

function resetCallTimer() {
  callStartedAt = null;
  callAccumulatedMs = 0;
  callTimerEl.textContent = "00:00";
}

function formatElapsed(ms) {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function updateCallTimerDisplay() {
  const runningMs = callStartedAt ? Date.now() - callStartedAt : 0;
  callTimerEl.textContent = formatElapsed(callAccumulatedMs + runningMs);
}

function startCallTimer() {
  if (!callStartedAt) {
    callStartedAt = Date.now();
  }
  if (!timerIntervalId) {
    timerIntervalId = window.setInterval(updateCallTimerDisplay, 250);
  }
  updateCallTimerDisplay();
}

function stopCallTimer() {
  if (callStartedAt) {
    callAccumulatedMs += Date.now() - callStartedAt;
    callStartedAt = null;
  }
  if (timerIntervalId) {
    window.clearInterval(timerIntervalId);
    timerIntervalId = null;
  }
  updateCallTimerDisplay();
}

function setLevel(percent) {
  const bounded = Math.max(0, Math.min(100, percent));
  levelFillEl.style.width = `${bounded}%`;
  levelValueEl.textContent = `${Math.round(bounded)}%`;
}

function stopLevelMeter() {
  if (levelAnimationId) {
    cancelAnimationFrame(levelAnimationId);
    levelAnimationId = null;
  }
  analyserNode = null;
  levelDataArray = null;
  setLevel(0);
}

async function ensurePlaybackContext() {
  if (!playbackCtx) {
    playbackCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 24000 });
    playbackGainNode = playbackCtx.createGain();
    playbackGainNode.gain.value = 1.0;
    playbackGainNode.connect(playbackCtx.destination);
  }
  if (playbackCtx.state === "suspended") {
    await playbackCtx.resume();
  }
  playbackScheduledAt = Math.max(playbackScheduledAt, playbackCtx.currentTime);
  return playbackCtx;
}

function stopPlaybackQueue() {
  for (const source of playbackSources) {
    try {
      source.stop();
    } catch (_) {
      // no-op
    }
  }
  playbackSources.clear();
  playbackScheduledAt = playbackCtx ? playbackCtx.currentTime : 0;
}

function decodeBase64ToInt16(base64) {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }
  return new Int16Array(bytes.buffer, bytes.byteOffset, Math.floor(bytes.byteLength / 2));
}

async function playPcmChunk(base64, sampleRate) {
  if (!base64) return;
  const ctx = await ensurePlaybackContext();
  const samples = decodeBase64ToInt16(base64);
  if (!samples.length) return;

  const audioBuffer = ctx.createBuffer(1, samples.length, sampleRate || 24000);
  const channel = audioBuffer.getChannelData(0);
  for (let i = 0; i < samples.length; i += 1) {
    channel[i] = samples[i] / 32768;
  }

  const source = ctx.createBufferSource();
  source.buffer = audioBuffer;
  source.connect(playbackGainNode);

  const startAt = Math.max(ctx.currentTime + 0.01, playbackScheduledAt || ctx.currentTime);
  const turnId = activeAssistantTurnId ? String(activeAssistantTurnId) : "";
  if (turnId && !playbackReportedTurns.has(turnId)) {
    playbackReportedTurns.add(turnId);
    const timeline = {};
    const currentText = timelineViewEl?.textContent || "";
    const keyMap = {
      0: "t0_submit",
      1: "t1_prepare_state_done",
      2: "t2_router_done",
      3: "t3_turn_plan_done",
      4: "t4_first_token",
      5: "t5_first_tts_submit",
      6: "t6_first_tts_chunk",
      7: "t7_first_push_pcm",
      8: "t8_frontend_playback",
    };
    for (const line of currentText.split("\n")) {
      const matched = line.match(/^t(\d)\s.+?:\s(\d+)ms$/);
      if (!matched) continue;
      const key = keyMap[Number(matched[1])];
      if (key) {
        timeline[key] = Number(matched[2]);
      }
    }
    const basePushMs = Number(timeline.t7_first_push_pcm || timeline.t6_first_tts_chunk || timeline.t5_first_tts_submit || 0);
    timeline.t8_frontend_playback = Math.round(basePushMs + Math.max(0, startAt - ctx.currentTime) * 1000);
    setCodeText(timelineViewEl, formatTimelineMap(timeline), "无");
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(
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
  playbackScheduledAt = startAt + audioBuffer.duration;
  playbackSources.add(source);
  source.onended = () => {
    playbackSources.delete(source);
  };
}

function startLevelMeter() {
  if (!analyserNode || !levelDataArray) return;

  const tick = () => {
    if (!analyserNode || !levelDataArray) return;
    analyserNode.getByteTimeDomainData(levelDataArray);
    let sum = 0;
    for (let i = 0; i < levelDataArray.length; i += 1) {
      const normalized = (levelDataArray[i] - 128) / 128;
      sum += normalized * normalized;
    }
    const rms = Math.sqrt(sum / levelDataArray.length);
    setLevel(Math.min(100, rms * 220));
    levelAnimationId = requestAnimationFrame(tick);
  };
  tick();
}

function updateConnectButton() {
  const isOpen = !!ws && ws.readyState === WebSocket.OPEN;
  btnConnect.textContent = isOpen ? "断开会话" : "连接会话";
  btnConnect.className = isOpen ? "btn-live" : "btn-primary";
  btnConnect.setAttribute("aria-pressed", isOpen ? "true" : "false");
  updateAttachmentState();
}

function updateMicButton() {
  btnMic.textContent = isMicActive ? "关闭麦克风" : "开启麦克风";
  btnMic.className = isMicActive ? "btn-live" : "btn-accent";
  btnMic.setAttribute("aria-pressed", isMicActive ? "true" : "false");
  setPillValue(micStateEl, isMicActive ? "采集中" : "未开启", isMicActive ? "ok" : "muted");
}

function updateMuteButton() {
  btnMute.textContent = isMuted ? "取消静音" : "静音麦克风";
  btnMute.className = isMuted ? "btn-warning" : "btn-soft";
  btnMute.setAttribute("aria-pressed", isMuted ? "true" : "false");
  setPillValue(muteStateEl, isMuted ? "已静音" : "未静音", isMuted ? "warn" : "muted");
}

function clearAttachments(options = {}) {
  const { sync = true } = options;
  pendingAttachments = [];
  attachmentInputEl.value = "";
  if (attachmentUrlInputEl) {
    attachmentUrlInputEl.value = "";
  }
  renderAttachmentList();
  if (sync) {
    syncStagedAttachments();
  }
}

function renderAttachmentList() {
  attachmentListEl.innerHTML = "";
  for (const [index, item] of pendingAttachments.entries()) {
    const wrapper = document.createElement("div");
    wrapper.className = "attachment-item";

    const head = document.createElement("div");
    head.className = "attachment-head";

    const meta = document.createElement("div");
    meta.className = "attachment-meta";
    meta.innerHTML = `
      <span class="attachment-name">${item.name}</span>
      <span class="attachment-desc">${describeAttachment(item)} · ${item.uri ? "URL" : formatBytes(item.size_bytes)}</span>
    `;
    head.appendChild(meta);

    const removeBtn = document.createElement("button");
    removeBtn.className = "btn-soft";
    removeBtn.textContent = "移除";
    removeBtn.addEventListener("click", () => {
      pendingAttachments.splice(index, 1);
      renderAttachmentList();
      syncStagedAttachments();
    });
    head.appendChild(removeBtn);
    wrapper.appendChild(head);

    if ((item.mime_type || "").startsWith("image/")) {
      const preview = document.createElement("div");
      preview.className = "attachment-preview";
      const img = document.createElement("img");
      img.src = item.preview_url;
      img.alt = item.name;
      preview.appendChild(img);
      wrapper.appendChild(preview);
    } else if ((item.mime_type || "").startsWith("audio/")) {
      const preview = document.createElement("div");
      preview.className = "attachment-preview";
      const audio = document.createElement("audio");
      audio.controls = true;
      audio.src = item.preview_url;
      preview.appendChild(audio);
      wrapper.appendChild(preview);
    } else if ((item.mime_type || "").startsWith("video/")) {
      const preview = document.createElement("div");
      preview.className = "attachment-preview";
      const video = document.createElement("video");
      video.controls = true;
      video.src = item.preview_url;
      preview.appendChild(video);
      wrapper.appendChild(preview);
    }

    if (item.uri) {
      const source = document.createElement("a");
      source.className = "hint";
      source.href = item.uri;
      source.target = "_blank";
      source.rel = "noreferrer noopener";
      source.textContent = item.uri;
      wrapper.appendChild(source);
    }

    attachmentListEl.appendChild(wrapper);
  }
  updateAttachmentState();
}

function dataUrlToBase64(dataUrl) {
  const idx = dataUrl.indexOf(",");
  return idx >= 0 ? dataUrl.slice(idx + 1) : dataUrl;
}

function inlineSourceToBase64(source) {
  return typeof source === "string" && source.startsWith("data:") ? dataUrlToBase64(source) : "";
}

function normalizeAttachmentUrl(raw) {
  const value = String(raw || "").trim();
  if (!value) return "";
  let parsed;
  try {
    parsed = new URL(value);
  } catch {
    return "";
  }
  if (!["http:", "https:"].includes(parsed.protocol)) return "";
  if (parsed.hostname === "github.com") {
    const parts = parsed.pathname.split("/").filter(Boolean);
    if (parts.length >= 5 && parts[2] === "blob") {
      const [owner, repo, , branch, ...rest] = parts;
      parsed = new URL(`https://raw.githubusercontent.com/${owner}/${repo}/${branch}/${rest.join("/")}`);
    }
  }
  const encodedPath = parsed.pathname
    .split("/")
    .map((segment) => {
      try {
        return encodeURIComponent(decodeURIComponent(segment));
      } catch {
        return encodeURIComponent(segment);
      }
    })
    .join("/");
  parsed.pathname = encodedPath;
  return parsed.toString();
}

function guessMimeTypeFromUrl(url) {
  const pathname = (() => {
    try {
      return new URL(url).pathname.toLowerCase();
    } catch {
      return "";
    }
  })();
  if (/\.(png|apng|jpg|jpeg|gif|webp|bmp|svg)$/.test(pathname)) return "image/png";
  if (/\.(mp3|wav|m4a|ogg)$/.test(pathname)) return "audio/mpeg";
  if (/\.(mp4|webm|mov|m4v)$/.test(pathname)) return "video/mp4";
  if (/\.pdf$/.test(pathname)) return "application/pdf";
  if (/\.md$/.test(pathname)) return "text/markdown";
  if (/\.json$/.test(pathname)) return "application/json";
  if (/\.txt$/.test(pathname)) return "text/plain";
  return "application/octet-stream";
}

function guessNameFromUrl(url, mimeType = "") {
  try {
    const pathname = new URL(url).pathname;
    const segments = pathname.split("/").filter(Boolean);
    const name = segments[segments.length - 1];
    if (name) return decodeURIComponent(name);
  } catch {}
  if ((mimeType || "").startsWith("image/")) return "remote-image";
  if ((mimeType || "").startsWith("audio/")) return "remote-audio";
  if ((mimeType || "").startsWith("video/")) return "remote-video";
  return "remote-attachment";
}

function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(reader.error || new Error("read file failed"));
    reader.readAsDataURL(file);
  });
}

async function handleAttachmentSelection(files) {
  const items = Array.from(files || []);
  for (const file of items) {
    const dataUrl = await readFileAsDataUrl(file);
    pendingAttachments.push({
      name: file.name,
      mime_type: file.type || "application/octet-stream",
      size_bytes: file.size,
      data_base64: dataUrlToBase64(dataUrl),
      preview_url: dataUrl,
    });
  }
  renderAttachmentList();
}

function addAttachmentFromUrl() {
  const normalized = normalizeAttachmentUrl(attachmentUrlInputEl?.value || "");
  if (!normalized) {
    log("invalid attachment url");
    return;
  }
  const mimeType = guessMimeTypeFromUrl(normalized);
  pendingAttachments.push({
    name: guessNameFromUrl(normalized, mimeType),
    mime_type: mimeType,
    size_bytes: 0,
    uri: normalized,
    preview_url: normalized,
    data_base64: "",
  });
  if (attachmentUrlInputEl) {
    attachmentUrlInputEl.value = "";
  }
  renderAttachmentList();
  syncStagedAttachments();
  log(`attachment url queued: ${normalized}`);
}

function syncStagedAttachments() {
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    updateAttachmentState();
    return;
  }
  const payload = buildAttachmentPayload();
  const message = payload.length
    ? { type: "stage_attachments", attachments: payload }
    : { type: "clear_staged_attachments" };
  ws.send(JSON.stringify(message));
  updateAttachmentState();
}

function renderHello(msg) {
  applySessionId(msg.session_id || getDesiredSessionId(), { persist: true, reflectCurrent: true });
  audioSpecEl.textContent = JSON.stringify(msg.audio || {});
  const playerUrl = msg.player_url || "-";
  playerUrlEl.textContent = playerUrl;
  playerUrlEl.href = playerUrl === "-" ? "#" : playerUrl;
  if (playerUrl !== "-") {
    playerFrameEl.src = playerUrl;
  } else {
    playerFrameEl.src = "about:blank";
  }
  if (Array.isArray(msg.history)) {
    clearTranscript();
    for (const item of msg.history) {
      if (!item || !item.role) continue;
      addMessage(item.role, item.text || item.summary || "", {
        key: item.key || `${item.role}-${Date.now()}-${localMessageSeq++}`,
        attachments: item.artifacts || [],
        meta: item.meta || null,
      });
    }

    const latestMeta = [...msg.history]
      .reverse()
      .find((item) => item && item.meta && Object.keys(item.meta).length)?.meta;
    if (latestMeta) {
      setCodeText(currentBranchEl, latestMeta.branch || "-");
      setCodeText(currentStrategyEl, latestMeta.strategy_id || "-");
      setCodeText(currentStrategyNameEl, latestMeta.strategy_name || "-");
      setCodeText(currentDeliveryEl, latestMeta.delivery_mode || "-");
      setCodeText(currentUiModeEl, latestMeta.ui_mode || "-");
      setCodeText(currentFollowupTypeEl, latestMeta.user_followup_type || "-");
      setCodeText(currentRenderTemplateEl, latestMeta.render_template || "-");
      setCodeText(currentStrategySourceEl, latestMeta.strategy_source || "-");
    }
  }
  if (Array.isArray(msg.staged_attachments) && msg.staged_attachments.length && !pendingAttachments.length) {
    pendingAttachments = msg.staged_attachments.map((item) => ({
      ...item,
      preview_url: getAttachmentPreviewSource(item),
      data_base64: inlineSourceToBase64(getAttachmentPreviewSource(item)),
      size_bytes: Number(item.size_bytes || 0),
    }));
    renderAttachmentList();
  }
  if (pendingAttachments.length) {
    syncStagedAttachments();
  } else {
    updateAttachmentState();
  }
  log(`hello(${compactValue(msg.session_id, getDesiredSessionId())}): ${msg.note || ""}`);
}

function handleEvent(msg) {
  if (msg.type === "hello") {
    renderHello(msg);
    return;
  }
  if (msg.type === "pong") {
    log("pong");
    return;
  }
  if (msg.type === "asr_partial") {
    setLiveText(partialEl, msg.text, "等待实时识别...");
    upsertPartialDraft(msg.text);
    return;
  }
  if (msg.type === "asr_final") {
    setLiveText(finalEl, msg.text, "等待最终转写...");
    setLiveText(partialEl, "", "等待实时识别...");
    flushPartialDraft();
    const text = (msg.text || "").trim();
    const attachments = Array.isArray(msg.attachments) ? msg.attachments : [];
    if (text || attachments.length) {
      const key = `user-final-${msg.ts || Date.now()}-${text || attachments.map((item) => item.name || "").join("-")}`;
      addMessage("user", text || attachmentSummary(attachments), { key, attachments });
    }
    return;
  }
  if (msg.type === "assistant_token") {
    const turnKey = String(msg.turn_id || "");
    if (turnKey && interruptedAssistantTurns.has(turnKey)) {
      return;
    }
    setSpeakerState("正在播报", "ok");
    appendAssistantToken(msg.turn_id, msg.token || "");
    return;
  }
  if (msg.type === "tts_chunk") {
    const turnKey = String(msg.turn_id || "");
    if (turnKey && interruptedAssistantTurns.has(turnKey)) {
      return;
    }
    playPcmChunk(msg.pcm_base64, msg.sample_rate || 24000).catch((error) => {
      log(`audio play failed: ${String(error?.message || error)}`);
    });
    return;
  }
  if (msg.type === "assistant_completed") {
    const turnKey = String(msg.turn_id || "");
    if (msg.interrupted && turnKey) {
      interruptedAssistantTurns.add(turnKey);
    }
    finishAssistant(msg.turn_id, !!msg.interrupted, msg.text || "");
    if (msg.interrupted) {
      log("assistant interrupted");
    }
    return;
  }
  if (msg.type === "state") {
    const state = msg.state || "-";
    const className =
      state === "speaking" ? "ok" :
      state === "interrupting" ? "warn" :
      state === "thinking" ? "warn" :
      state === "shutdown" ? "danger" :
      "muted";
    setPillValue(sessionStateEl, state, className);
    if (state === "listening") {
      setSpeakerState("等待回复", "muted");
    }
    return;
  }
  if (msg.type === "route") {
    const strategy = msg.strategy_id ? ` / ${msg.strategy_id}` : "";
    log(`route: ${msg.turn_scene} (${Number(msg.confidence || 0).toFixed(2)})${strategy}`);
    setCodeText(currentRouteEl, `${msg.turn_scene || "-"} / ${msg.session_scene || "-"}`);
    setCodeText(currentBranchEl, msg.turn_scene || "-");
    setCodeText(currentStrategyEl, msg.strategy_id || "-");
    setCodeText(currentDeliveryEl, msg.delivery_mode || "-");
    setCodeText(currentUiModeEl, msg.ui_mode || "-");
    setCodeText(
      currentHandlerEl,
      `${msg.handler || "-"}${msg.strategy_id ? ` / ${msg.strategy_id}` : ""}`
    );
    if (msg.turn_id !== undefined && msg.turn_id !== null) {
      activeAssistantTurnId = String(msg.turn_id);
      interruptedAssistantTurns.delete(activeAssistantTurnId);
    }
    ensureAssistantMessage(msg.turn_id);
    setMessageMeta(msg.turn_id, {
      branch: msg.turn_scene || "",
      strategy_id: msg.strategy_id || "",
      delivery_mode: msg.delivery_mode || "",
      ui_mode: msg.ui_mode || "",
    });
    return;
  }
  if (msg.type === "debug_strategy") {
    setCodeText(currentBranchEl, msg.branch || "-");
    setCodeText(currentStrategyEl, msg.strategy_id || "-");
    setCodeText(currentStrategyNameEl, msg.strategy_name || "-");
    setCodeText(currentDeliveryEl, msg.delivery_mode || "-");
    setCodeText(currentUiModeEl, msg.ui_mode || "-");
    setCodeText(currentFollowupTypeEl, msg.user_followup_type || "-");
    setCodeText(currentRenderTemplateEl, msg.render_template || "-");
    setCodeText(currentStrategySourceEl, msg.strategy_source || "-");
    setCodeText(currentArtifactSubjectHintEl, msg.artifact_subject_hint || "-");
    setCodeText(currentArtifactTaskHintEl, msg.artifact_task_hint || "-");
    setCodeText(artifactTextViewEl, msg.artifact_text || "无");
    ensureAssistantMessage(msg.turn_id);
    setMessageMeta(msg.turn_id, {
      branch: msg.branch || "",
      strategy_id: msg.strategy_id || "",
      strategy_name: msg.strategy_name || "",
      delivery_mode: msg.delivery_mode || "",
      ui_mode: msg.ui_mode || "",
      user_followup_type: msg.user_followup_type || "",
      render_template: msg.render_template || "",
      strategy_source: msg.strategy_source || "",
    });
    if (msg.strategy_name) {
      log(`strategy: ${msg.strategy_id} (${msg.strategy_name})`);
    }
    return;
  }
  if (msg.type === "debug_context") {
    setCodeText(multimodalSummaryEl, msg.multimodal_summary || "无");
    setCodeText(memorySummaryEl, msg.memory_summary || "无");
    setCodeText(historySummaryEl, msg.history_summary || "无");
    setCodeText(factsViewEl, JSON.stringify(msg.facts || {}, null, 2), "{}");
    return;
  }
  if (msg.type === "debug_prompt") {
    setCodeText(
      currentHandlerEl,
      `${msg.handler || "-"}${msg.strategy_id ? ` / ${msg.strategy_id}` : ""}`
    );
    setCodeText(currentRenderTemplateEl, msg.render_template || "-");
    setCodeText(currentDeliveryEl, msg.delivery_mode || "-");
    setCodeText(currentUiModeEl, msg.ui_mode || "-");
    setCodeText(promptViewEl, msg.system_prompt || "无");
    return;
  }
  if (msg.type === "debug_metrics") {
    setMetricValue(metricAsrFinalLatencyEl, msg.asr_final_latency_ms);
    setMetricValue(metricFirstTokenLatencyEl, msg.first_token_latency_ms);
    setMetricValue(metricFirstAudioLatencyEl, msg.first_audio_latency_ms);
    setMetricValue(metricInterruptCountEl, msg.interrupt_count, (value) => `${Number(value || 0)}`);
    setCodeText(timelineViewEl, formatTimelineMap(msg.timeline_ms || {}), "无");
    return;
  }
  if (msg.type === "staged_attachments") {
    const count = Array.isArray(msg.attachments) ? msg.attachments.length : 0;
    if (Array.isArray(msg.attachments)) {
      pendingAttachments = msg.attachments.map((item) => ({
        ...item,
        preview_url: getAttachmentPreviewSource(item),
        data_base64: inlineSourceToBase64(getAttachmentPreviewSource(item)),
        size_bytes: Number(item.size_bytes || 0),
      }));
      renderAttachmentList();
    }
    updateAttachmentState();
    log(`staged attachments: ${count}`);
    return;
  }
  if (msg.type === "control") {
    log(`control: ${msg.action}${msg.detail ? ` (${msg.detail})` : ""}`);
    if (msg.action === "start_turn") {
      flushPartialDraft();
      setSpeakerState("准备回复", "warn");
      if (msg.turn_id !== undefined && msg.turn_id !== null) {
        activeAssistantTurnId = String(msg.turn_id);
        interruptedAssistantTurns.delete(activeAssistantTurnId);
      }
    }
    if (msg.action === "interrupt") {
      setSpeakerState("已打断", "warn");
      if (msg.turn_id !== undefined && msg.turn_id !== null) {
        interruptedAssistantTurns.add(String(msg.turn_id));
      }
      stopPlaybackQueue();
    }
    return;
  }
  if (msg.type === "error") {
    log(`server error: ${msg.scope || "server"} ${msg.message}`);
    return;
  }
  log(`msg: ${JSON.stringify(msg)}`);
}

function attachSocket(socket) {
  ws = socket;
  ws.binaryType = "arraybuffer";
  setPillValue(connStateEl, "连接中...", "warn");
  updateConnectButton();

  ws.onopen = () => {
    setPillValue(connStateEl, "已连接", "ok");
    updateConnectButton();
    log("WS open");
    ws.send(JSON.stringify({ type: "ping" }));
  };

  ws.onclose = async () => {
    setPillValue(connStateEl, "已断开", "muted");
    setPillValue(sessionStateEl, "-", "muted");
    updateConnectButton();
    log("WS close");
    stopPlaybackQueue();
    await stopMicrophone();
    updateAttachmentState();
  };

  ws.onerror = (event) => {
    log(`WS error: ${String(event?.message || event)}`);
  };

  ws.onmessage = (evt) => {
    try {
      handleEvent(JSON.parse(evt.data));
    } catch {
      log(`text: ${evt.data}`);
    }
  };
}

function connectSocket() {
  if (ws && ws.readyState === WebSocket.OPEN) {
    return Promise.resolve(ws);
  }
  if (connectPromise) {
    return connectPromise;
  }

  connectPromise = new Promise((resolve, reject) => {
    const socket = new WebSocket(buildWsUrl());
    attachSocket(socket);

    const cleanup = () => {
      connectPromise = null;
    };

    socket.addEventListener("open", () => {
      cleanup();
      resolve(socket);
    }, { once: true });

    socket.addEventListener("error", (error) => {
      cleanup();
      reject(error);
    }, { once: true });

    socket.addEventListener("close", () => {
      cleanup();
    }, { once: true });
  });

  return connectPromise;
}

async function ensureConnected() {
  if (ws && ws.readyState === WebSocket.OPEN) {
    return ws;
  }
  return connectSocket();
}

async function startMicrophone() {
  if (isMicActive) return;
  await ensureConnected();
  await ensurePlaybackContext();

  mediaStream = await navigator.mediaDevices.getUserMedia({
    audio: {
      channelCount: 1,
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
    },
    video: false,
  });

  audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  await audioCtx.audioWorklet.addModule("/static/audio-worklet.js");

  const source = audioCtx.createMediaStreamSource(mediaStream);
  analyserNode = audioCtx.createAnalyser();
  analyserNode.fftSize = 1024;
  levelDataArray = new Uint8Array(analyserNode.frequencyBinCount);

  workletNode = new AudioWorkletNode(audioCtx, "pcm-downsampler", {
    processorOptions: {
      targetSampleRate: TARGET_SAMPLE_RATE,
    },
    numberOfInputs: 1,
    numberOfOutputs: 0,
    channelCount: 1,
  });

  workletNode.port.onmessage = (evt) => {
    if (!ws || ws.readyState !== WebSocket.OPEN || isMuted) {
      return;
    }
    const buf = evt.data;
    if (buf && buf.byteLength) {
      ws.send(buf);
    }
  };

  source.connect(analyserNode);
  source.connect(workletNode);
  startLevelMeter();
  startCallTimer();
  isMicActive = true;
  updateMicButton();
  log(`Mic start: AudioContext sampleRate=${audioCtx.sampleRate}`);
}

async function stopMicrophone() {
  if (!audioCtx && !mediaStream && !workletNode) {
    isMicActive = false;
    updateMicButton();
    stopCallTimer();
    stopLevelMeter();
    return;
  }
  try {
    if (workletNode) {
      workletNode.port.onmessage = null;
      workletNode.disconnect();
      workletNode = null;
    }
    if (analyserNode) {
      analyserNode.disconnect();
      analyserNode = null;
    }
    if (audioCtx) {
      await audioCtx.close();
      audioCtx = null;
    }
    if (mediaStream) {
      mediaStream.getTracks().forEach((track) => track.stop());
      mediaStream = null;
    }
  } finally {
    isMicActive = false;
    updateMicButton();
    stopCallTimer();
    stopLevelMeter();
    if (ws && ws.readyState === WebSocket.OPEN) {
      try {
        ws.send(JSON.stringify({ type: "mic_stopped" }));
      } catch (error) {
        log(`mic stop commit failed: ${String(error?.message || error)}`);
      }
    }
    log("Mic stopped");
  }
}

async function toggleSocket() {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.close();
    return;
  }
  try {
    await ensurePlaybackContext();
    await connectSocket();
  } catch (error) {
    log(`connect failed: ${String(error?.message || error)}`);
  }
}

async function applySessionSwitch() {
  const nextSessionId = applySessionId(getDesiredSessionId(), { persist: true, reflectCurrent: false });
  if (ws && ws.readyState === WebSocket.OPEN) {
    if (isMicActive) {
      await stopMicrophone();
    }
    ws.close();
    log(`session switch requested: ${nextSessionId}`);
    window.setTimeout(() => {
      connectSocket().catch((error) => {
        log(`session reconnect failed: ${String(error?.message || error)}`);
      });
    }, 120);
    return;
  }
  setCodeText(currentSessionIdEl, nextSessionId);
  log(`session prepared: ${nextSessionId}`);
}

async function toggleMicrophone() {
  try {
    if (isMicActive) {
      await stopMicrophone();
    } else {
      await startMicrophone();
    }
  } catch (error) {
    log(`mic error: ${String(error?.message || error)}`);
    await stopMicrophone();
  }
}

function toggleMute() {
  isMuted = !isMuted;
  updateMuteButton();
  log(isMuted ? "Mic muted" : "Mic unmuted");
}

function interruptPlayback() {
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    log("WS 未连接，无法 interrupt");
    return;
  }
  stopPlaybackQueue();
  ws.send(JSON.stringify({ type: "interrupt" }));
}

function buildAttachmentPayload() {
  return pendingAttachments.map((item) => ({
    name: item.name,
    mime_type: item.mime_type,
    data_base64: item.data_base64 || inlineSourceToBase64(getAttachmentPreviewSource(item)),
    uri: item.uri || "",
    summary: item.summary || "",
  }));
}

async function sendTextMessage() {
  const text = textInputEl.value.trim();
  const attachments = buildAttachmentPayload();
  if (!text && !attachments.length) {
    return;
  }
  try {
    await ensurePlaybackContext();
    await ensureConnected();
    ws.send(JSON.stringify({ type: "text", text, attachments }));
    addMessage("user", text || attachmentSummary(pendingAttachments), {
      attachments: pendingAttachments,
      key: `user-local-${Date.now()}-${localMessageSeq++}`,
    });
    textInputEl.value = "";
    log(`text send: ${text ? text.slice(0, 48) : "[attachments]"}`);
  } catch (error) {
    log(`send failed: ${String(error?.message || error)}`);
  }
}

function buildStrategyContextText() {
  const attachmentLines = pendingAttachments.length
    ? pendingAttachments.map((item) => `- ${describeAttachment(item)}: ${item.name}`).join("\n")
    : "无";
  const activeSessionId = compactValue(currentSessionIdEl?.textContent, getDesiredSessionId());
  return [
    `session_id: ${activeSessionId}`,
    `route: ${compactValue(currentRouteEl?.textContent)}`,
    `handler: ${compactValue(currentHandlerEl?.textContent)}`,
    `branch: ${compactValue(currentBranchEl?.textContent)}`,
    `strategy_id: ${compactValue(currentStrategyEl?.textContent)}`,
    `strategy_name: ${compactValue(currentStrategyNameEl?.textContent)}`,
    `delivery_mode: ${compactValue(currentDeliveryEl?.textContent)}`,
    `ui_mode: ${compactValue(currentUiModeEl?.textContent)}`,
    `user_followup_type: ${compactValue(currentFollowupTypeEl?.textContent)}`,
    `render_template: ${compactValue(currentRenderTemplateEl?.textContent)}`,
    `strategy_source: ${compactValue(currentStrategySourceEl?.textContent)}`,
    `artifact_subject_hint: ${compactValue(currentArtifactSubjectHintEl?.textContent)}`,
    `artifact_task_hint: ${compactValue(currentArtifactTaskHintEl?.textContent)}`,
    "",
    "attachments:",
    attachmentLines,
    "",
    "multimodal_summary:",
    compactValue(multimodalSummaryEl?.textContent, "无"),
    "",
    "artifact_text:",
    compactValue(artifactTextViewEl?.textContent, "无"),
    "",
    "memory_summary:",
    compactValue(memorySummaryEl?.textContent, "无"),
    "",
    "history_summary:",
    compactValue(historySummaryEl?.textContent, "无"),
    "",
    "facts:",
    compactValue(factsViewEl?.textContent, "{}"),
    "",
    "system_prompt:",
    compactValue(promptViewEl?.textContent, "无"),
    "",
    "turn_timeline:",
    compactValue(timelineViewEl?.textContent, "无"),
  ].join("\n");
}

async function copyStrategyContext() {
  const text = buildStrategyContextText();
  try {
    await navigator.clipboard.writeText(text);
    log("strategy context copied");
  } catch (error) {
    const fallback = document.createElement("textarea");
    fallback.value = text;
    fallback.setAttribute("readonly", "readonly");
    fallback.style.position = "fixed";
    fallback.style.opacity = "0";
    document.body.appendChild(fallback);
    fallback.select();
    try {
      document.execCommand("copy");
      log("strategy context copied");
    } catch (copyError) {
      log(`copy failed: ${String(copyError?.message || error?.message || copyError || error)}`);
    } finally {
      document.body.removeChild(fallback);
    }
  }
}

btnConnect.addEventListener("click", toggleSocket);
if (btnApplySession) {
  btnApplySession.addEventListener("click", () => {
    applySessionSwitch();
  });
}
btnMic.addEventListener("click", toggleMicrophone);
btnMute.addEventListener("click", toggleMute);
btnInterrupt.addEventListener("click", interruptPlayback);
btnClear.addEventListener("click", () => {
  clearTranscript();
  setLiveText(partialEl, "", "等待实时识别...");
  setLiveText(finalEl, "", "等待最终转写...");
  clearAttachments();
  log("local transcript cleared");
});
btnSend.addEventListener("click", sendTextMessage);
btnPickAttachment.addEventListener("click", () => attachmentInputEl.click());
if (btnAddAttachmentUrl) {
  btnAddAttachmentUrl.addEventListener("click", addAttachmentFromUrl);
}
btnClearAttachment.addEventListener("click", clearAttachments);
if (btnCopyStrategyContext) {
  btnCopyStrategyContext.addEventListener("click", () => {
    copyStrategyContext();
  });
}

attachmentInputEl.addEventListener("change", async (event) => {
  const files = event.target.files;
  if (!files || !files.length) return;
  try {
    await handleAttachmentSelection(files);
    syncStagedAttachments();
    log(`attachments queued: ${files.length}`);
  } catch (error) {
    log(`attachment read failed: ${String(error?.message || error)}`);
  }
});

if (attachmentUrlInputEl) {
  attachmentUrlInputEl.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      addAttachmentFromUrl();
    }
  });
}

if (sessionIdInputEl) {
  sessionIdInputEl.addEventListener("change", () => {
    applySessionId(sessionIdInputEl.value, { persist: true, reflectCurrent: false });
  });
  sessionIdInputEl.addEventListener("blur", () => {
    applySessionId(sessionIdInputEl.value, { persist: true, reflectCurrent: false });
  });
}

textInputEl.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendTextMessage();
  }
});

window.addEventListener("beforeunload", () => {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.close();
  }
  stopPlaybackQueue();
});

applySessionId(localStorage.getItem(SESSION_STORAGE_KEY) || "default", { persist: false, reflectCurrent: true });
updateConnectButton();
updateMicButton();
updateMuteButton();
resetCallTimer();
setPillValue(connStateEl, "未连接", "muted");
setPillValue(sessionStateEl, "-", "muted");
setSpeakerState("等待回复", "muted");
setLiveText(partialEl, "", "等待实时识别...");
setLiveText(finalEl, "", "等待最终转写...");
setCodeText(currentRouteEl, "-", "-");
setCodeText(currentHandlerEl, "-", "-");
setCodeText(currentBranchEl, "-", "-");
setCodeText(currentStrategyEl, "-", "-");
setCodeText(currentStrategyNameEl, "-", "-");
setCodeText(currentDeliveryEl, "-", "-");
setCodeText(currentUiModeEl, "-", "-");
setCodeText(currentFollowupTypeEl, "-", "-");
setCodeText(currentRenderTemplateEl, "-", "-");
setCodeText(currentStrategySourceEl, "-", "-");
setCodeText(currentArtifactSubjectHintEl, "-", "-");
setCodeText(currentArtifactTaskHintEl, "-", "-");
setCodeText(multimodalSummaryEl, "无");
setCodeText(artifactTextViewEl, "无");
setCodeText(memorySummaryEl, "无");
setCodeText(historySummaryEl, "无");
setCodeText(factsViewEl, "{}");
setCodeText(promptViewEl, "无");
setCodeText(timelineViewEl, "无");
setMetricValue(metricAsrFinalLatencyEl, null);
setMetricValue(metricFirstTokenLatencyEl, null);
setMetricValue(metricFirstAudioLatencyEl, null);
setMetricValue(metricInterruptCountEl, 0, (value) => `${Number(value || 0)}`);
setLevel(0);
updateAttachmentState();
