import { el } from "./dom.js";
import { state } from "./store.js";
import { SESSION_STORAGE_KEY } from "./config.js";
import { compactValue, normalizeSessionId, setPill, setSpeakerState, setText, normalizeSkillNames } from "./utils.js";
import { log } from "./log.js";
import {
  addMessage,
  appendAssistantToken,
  attachmentSummary,
  clearTranscript,
  ensureAssistantMessage,
  finishAssistant,
  flushPartialDraft,
  normalizeUserMessageContent,
  setMessageMeta,
  updateHistoryPanelSummary,
  upsertPartialDraft,
  userMessageToAttachments,
  userMessageToDisplayText,
} from "./transcript.js";
import {
  applyPromptProfile,
  renderDebugContext,
  renderDebugPrompt,
  renderHelloMeta,
  renderMetrics,
  renderPipelineDebug,
  renderPromptPackage,
  renderRouteMeta,
  renderSessionState,
} from "./panels.js";
import {
  ensurePlaybackContext,
  playPcmChunk,
  stopMicrophone,
  stopPlaybackQueue,
} from "./audio.js";
import { buildAttachmentPayload, hydrateFromServer, syncStagedAttachments, updateAttachmentState } from "./attachments.js";

export function getDesiredSessionId() {
  return normalizeSessionId(
    el("sessionId")?.value || localStorage.getItem(SESSION_STORAGE_KEY) || "default"
  );
}

export function buildWsUrl() {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  const url = new URL(`${proto}//${location.host}/ws/audio`);
  url.searchParams.set("session_id", getDesiredSessionId());
  return url.toString();
}

export function applySessionId(value, { persist = true, reflectCurrent = false } = {}) {
  const normalized = normalizeSessionId(value);
  const input = el("sessionId");
  if (input) input.value = normalized;
  if (persist) localStorage.setItem(SESSION_STORAGE_KEY, normalized);
  if (reflectCurrent) setText("currentSessionId", normalized);
  setText("wsUrl", buildWsUrl());
  return normalized;
}

export function updateConnectButton() {
  const btn = el("btnConnect");
  if (!btn) return;
  const isOpen = !!state.ws && state.ws.readyState === WebSocket.OPEN;
  btn.textContent = isOpen ? "断开会话" : "连接会话";
  btn.classList.toggle("active", isOpen);
  btn.setAttribute("aria-pressed", isOpen ? "true" : "false");
  updateAttachmentState();
}

function renderHello(msg) {
  applySessionId(msg.session_id || getDesiredSessionId(), { persist: true, reflectCurrent: true });
  setText("audioSpec", JSON.stringify(msg.audio || {}));
  const playerUrl = msg.player_url || "-";
  const playerLink = el("playerUrl");
  if (playerLink) {
    playerLink.textContent = playerUrl;
    playerLink.href = playerUrl === "-" ? "#" : playerUrl;
  }
  if (Array.isArray(msg.history)) {
    clearTranscript();
    for (const item of msg.history) {
      if (!item || !item.role) continue;
      addMessage(item.role, "", {
        key: item.key || `${item.role}-${Date.now()}-${state.localMessageSeq++}`,
        attachments: item.artifacts || [],
        contentBlocks: item.content || [],
        meta: item.meta || null,
        timestamp: item.created_at || item.ts || item.timestamp || Date.now(),
        interrupted: item.role === "assistant" && (item.meta || {}).turn_status === "interrupted",
      });
    }
    const latestMeta = [...msg.history]
      .reverse()
      .find((item) => item && item.meta && Object.keys(item.meta).length)?.meta;
    if (latestMeta) renderHelloMeta(latestMeta);
    updateHistoryPanelSummary();
  }
  if (Array.isArray(msg.staged_attachments) && msg.staged_attachments.length && !state.pendingAttachments.length) {
    hydrateFromServer(msg.staged_attachments);
  }
  if (state.pendingAttachments.length) {
    syncStagedAttachments();
  } else {
    updateAttachmentState();
  }
  log(`会话已建立（${compactValue(msg.session_id, getDesiredSessionId())}）：${msg.note || ""}`, "ok");
}

function handleRoute(msg) {
  const task = String((msg.prompt_profile || {}).task || "").trim();
  log(`路由结果：${msg.turn_scene}（${Number(msg.confidence || 0).toFixed(2)}）${task ? ` / ${task}` : ""}`);
  renderRouteMeta(msg);
  applyPromptProfile(msg.prompt_profile || {});
  if (msg.turn_id !== undefined && msg.turn_id !== null) {
    state.activeAssistantTurnId = String(msg.turn_id);
    state.interruptedAssistantTurns.delete(state.activeAssistantTurnId);
  }
  ensureAssistantMessage(msg.turn_id);
  setMessageMeta(msg.turn_id, {
    session_scene: msg.session_scene || "",
    turn_scene: msg.turn_scene || "",
    capability: (msg.prompt_profile || {}).capability || "",
    task: (msg.prompt_profile || {}).task || "",
    knowledge: (msg.prompt_profile || {}).knowledge || "",
    method: (msg.prompt_profile || {}).method || "",
    audience: (msg.prompt_profile || {}).audience || "",
    skills: normalizeSkillNames(msg.active_skills || (msg.prompt_profile || {}).skills || []),
  });
}

function handleControl(msg) {
  log(`控制事件：${msg.action}${msg.detail ? `（${msg.detail}）` : ""}`);
  if (msg.action === "start_turn") {
    flushPartialDraft();
    setSpeakerState("准备回复", "warn");
    if (msg.turn_id !== undefined && msg.turn_id !== null) {
      state.activeAssistantTurnId = String(msg.turn_id);
      state.interruptedAssistantTurns.delete(state.activeAssistantTurnId);
    }
  }
  if (msg.action === "interrupt") {
    setSpeakerState("已打断", "warn");
    if (msg.turn_id !== undefined && msg.turn_id !== null) {
      state.interruptedAssistantTurns.add(String(msg.turn_id));
    }
    stopPlaybackQueue();
  }
  updateHistoryPanelSummary();
}

function handleEvent(msg) {
  switch (msg.type) {
    case "hello":
      renderHello(msg);
      return;
    case "pong":
      log("收到 pong");
      return;
    case "asr_partial": {
      const userMessage = msg.user_message || { role: "user", content: [] };
      setText("partial", userMessageToDisplayText(userMessage), "等待实时识别...");
      upsertPartialDraft(userMessage);
      return;
    }
    case "asr_final": {
      const userMessage = msg.user_message || { role: "user", content: [] };
      setText("final", userMessageToDisplayText(userMessage), "等待最终转写...");
      setText("partial", "", "等待实时识别...");
      flushPartialDraft();
      const text = userMessageToDisplayText(userMessage);
      const attachments = userMessageToAttachments(userMessage);
      const contentBlocks = normalizeUserMessageContent(userMessage.content || []);
      if (contentBlocks.length) {
        addMessage("user", text, {
          key: `user-final-${msg.ts || Date.now()}-${text || attachments.map((item) => item.name || "").join("-")}`,
          attachments,
          timestamp: msg.ts || Date.now(),
          contentBlocks,
        });
      }
      return;
    }
    case "assistant_token": {
      const turnKey = String(msg.turn_id || "");
      if (turnKey && state.interruptedAssistantTurns.has(turnKey)) return;
      setSpeakerState("正在播报", "ok");
      appendAssistantToken(msg.turn_id, msg.token || "");
      return;
    }
    case "tts_chunk": {
      const turnKey = String(msg.turn_id || "");
      if (turnKey && state.interruptedAssistantTurns.has(turnKey)) return;
      playPcmChunk(msg.pcm_base64, msg.sample_rate || 24000).catch((error) => {
        log(`音频播放失败：${String(error?.message || error)}`, "error");
      });
      return;
    }
    case "assistant_completed": {
      const turnKey = String(msg.turn_id || "");
      if (msg.interrupted && turnKey) state.interruptedAssistantTurns.add(turnKey);
      finishAssistant(msg.turn_id, !!msg.interrupted, msg.assistant_message || { role: "assistant", content: [] });
      if (msg.interrupted) log("助手回复已被打断", "warn");
      return;
    }
    case "state": {
      state.currentSessionState = msg.state || "idle";
      renderSessionState(msg.state);
      if (msg.state === "listening") setSpeakerState("等待回复", "muted");
      return;
    }
    case "route":
      handleRoute(msg);
      return;
    case "debug_prompt_package": {
      renderPromptPackage(msg);
      ensureAssistantMessage(msg.turn_id);
      setMessageMeta(msg.turn_id, {
        capability: (msg.prompt_profile || {}).capability || "",
        task: (msg.prompt_profile || {}).task || "",
        knowledge: (msg.prompt_profile || {}).knowledge || "",
        method: (msg.prompt_profile || {}).method || "",
        audience: (msg.prompt_profile || {}).audience || "",
        skills: normalizeSkillNames(msg.active_skills || (msg.prompt_profile || {}).skills || []),
        user_followup_type: msg.user_followup_type || "",
        prompt_source: msg.prompt_source || "",
      });
      updateHistoryPanelSummary();
      return;
    }
    case "debug_context":
      renderDebugContext(msg);
      return;
    case "debug_prompt":
      renderDebugPrompt(msg);
      return;
    case "debug_metrics":
      renderMetrics(msg);
      return;
    case "debug_pipeline":
      renderPipelineDebug(msg);
      return;
    case "staged_attachments": {
      const count = Array.isArray(msg.attachments) ? msg.attachments.length : 0;
      if (Array.isArray(msg.attachments)) hydrateFromServer(msg.attachments);
      updateAttachmentState();
      log(`暂存附件数量：${count}`);
      return;
    }
    case "control":
      handleControl(msg);
      return;
    case "error":
      log(`服务端错误：${msg.scope || "server"} ${msg.message}`, "error");
      return;
    default:
      log(`未识别消息：${JSON.stringify(msg)}`, "warn");
  }
}

function attachSocket(socket) {
  state.ws = socket;
  socket.binaryType = "arraybuffer";
  setPill("connState", "连接中...", "warn");
  updateConnectButton();

  socket.onopen = () => {
    setPill("connState", "已连接", "ok");
    updateConnectButton();
    log("实时连接已建立", "ok");
    socket.send(JSON.stringify({ type: "ping" }));
  };

  socket.onclose = async () => {
    setPill("connState", "已断开", "muted");
    setPill("sessionState", "-", "muted");
    state.currentSessionState = "idle";
    updateConnectButton();
    log("实时连接已断开", "warn");
    stopPlaybackQueue();
    await stopMicrophone();
    updateAttachmentState();
  };

  socket.onerror = (event) => {
    log(`实时连接错误：${String(event?.message || event)}`, "error");
  };

  socket.onmessage = (evt) => {
    try {
      handleEvent(JSON.parse(evt.data));
    } catch {
      log(`收到文本：${evt.data}`);
    }
  };
}

export function connectSocket() {
  if (state.ws && state.ws.readyState === WebSocket.OPEN) {
    return Promise.resolve(state.ws);
  }
  if (state.connectPromise) return state.connectPromise;

  state.connectPromise = new Promise((resolve, reject) => {
    const socket = new WebSocket(buildWsUrl());
    attachSocket(socket);
    const cleanup = () => {
      state.connectPromise = null;
    };
    socket.addEventListener("open", () => {
      cleanup();
      resolve(socket);
    }, { once: true });
    socket.addEventListener("error", (error) => {
      cleanup();
      reject(error);
    }, { once: true });
    socket.addEventListener("close", () => cleanup(), { once: true });
  });

  return state.connectPromise;
}

export async function ensureConnected() {
  if (state.ws && state.ws.readyState === WebSocket.OPEN) return state.ws;
  return connectSocket();
}

export async function toggleSocket() {
  if (state.ws && state.ws.readyState === WebSocket.OPEN) {
    state.ws.close();
    return;
  }
  try {
    await ensurePlaybackContext();
    await connectSocket();
  } catch (error) {
    log(`连接失败：${String(error?.message || error)}`, "error");
  }
}

export async function applySessionSwitch() {
  const nextSessionId = applySessionId(getDesiredSessionId(), { persist: true, reflectCurrent: false });
  if (state.ws && state.ws.readyState === WebSocket.OPEN) {
    if (state.isMicActive) await stopMicrophone();
    state.ws.close();
    log(`请求切换会话：${nextSessionId}`);
    window.setTimeout(() => {
      connectSocket().catch((error) => {
        log(`会话重连失败：${String(error?.message || error)}`, "error");
      });
    }, 120);
    return;
  }
  setText("currentSessionId", nextSessionId);
  log(`会话已准备就绪：${nextSessionId}`);
}

export async function sendTextMessage() {
  const input = el("textInput");
  const text = (input?.value || "").trim();
  const attachments = buildAttachmentPayload();
  if (!text && !attachments.length) return;
  try {
    await ensurePlaybackContext();
    await ensureConnected();
    state.ws.send(JSON.stringify({ type: "text", text, attachments }));
    addMessage("user", text || attachmentSummary(state.pendingAttachments), {
      attachments: state.pendingAttachments,
      key: `user-local-${Date.now()}-${state.localMessageSeq++}`,
    });
    if (input) input.value = "";
    log(`文本已发送：${text ? text.slice(0, 48) : "[仅附件]"}`);
  } catch (error) {
    log(`发送失败：${String(error?.message || error)}`, "error");
  }
}