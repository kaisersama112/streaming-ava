import { el } from "./dom.js";
import { state } from "./store.js";
import { SESSION_STORAGE_KEY } from "./config.js";
import { setPill, setSpeakerState, setText } from "./utils.js";
import { log } from "./log.js";
import {
  applySessionId,
  applySessionSwitch,
  sendTextMessage,
  toggleSocket,
  updateConnectButton,
} from "./connection.js";
import {
  interruptPlayback,
  resetCallTimer,
  stopPlaybackQueue,
  toggleMicrophone,
  toggleMute,
  updateMicButton,
  updateMuteButton,
} from "./audio.js";
import {
  addAttachmentFromUrl,
  clearAttachments,
  handleAttachmentSelection,
  syncStagedAttachments,
  updateAttachmentState,
} from "./attachments.js";
import { clearTranscript, flushPartialDraft } from "./transcript.js";
import { buildDebugContextText, renderTimeline } from "./panels.js";
import { initRouterTestPanel } from "./router_test.js";

function initTabs() {
  const buttons = [...document.querySelectorAll(".tab-btn")];
  const panels = [...document.querySelectorAll(".tab-panel")];
  for (const button of buttons) {
    button.addEventListener("click", () => {
      const target = button.dataset.tab;
      for (const item of buttons) item.classList.toggle("active", item === button);
      for (const panel of panels) panel.hidden = panel.dataset.panel !== target;
    });
  }
}

async function copyDebugContext() {
  const text = buildDebugContextText();
  try {
    await navigator.clipboard.writeText(text);
    log("调试上下文已复制", "ok");
  } catch {
    const fallback = document.createElement("textarea");
    fallback.value = text;
    fallback.setAttribute("readonly", "readonly");
    fallback.style.position = "fixed";
    fallback.style.opacity = "0";
    document.body.appendChild(fallback);
    fallback.select();
    try {
      document.execCommand("copy");
      log("调试上下文已复制", "ok");
    } catch (error) {
      log(`复制失败：${String(error?.message || error)}`, "error");
    } finally {
      document.body.removeChild(fallback);
    }
  }
}

function wireButtons() {
  el("btnConnect")?.addEventListener("click", toggleSocket);
  el("btnApplySession")?.addEventListener("click", () => applySessionSwitch());
  el("btnMic")?.addEventListener("click", toggleMicrophone);
  el("btnMute")?.addEventListener("click", toggleMute);
  el("btnInterrupt")?.addEventListener("click", () => interruptPlayback("manual"));
  el("btnSend")?.addEventListener("click", sendTextMessage);
  el("btnPickAttachment")?.addEventListener("click", () => el("attachmentInput")?.click());
  el("btnAddAttachmentUrl")?.addEventListener("click", addAttachmentFromUrl);
  el("btnClearAttachment")?.addEventListener("click", () => clearAttachments());
  el("btnCopyPromptContext")?.addEventListener("click", () => copyDebugContext());
  el("btnClear")?.addEventListener("click", () => {
    clearTranscript();
    setText("partial", "", "等待实时识别...");
    setText("final", "", "等待最终转写...");
    clearAttachments();
    log("本地转写记录已清空");
  });

  el("attachmentInput")?.addEventListener("change", async (event) => {
    const files = event.target.files;
    if (!files || !files.length) return;
    try {
      await handleAttachmentSelection(files);
      syncStagedAttachments();
      log(`已暂存附件：${files.length}`);
    } catch (error) {
      log(`附件读取失败：${String(error?.message || error)}`, "error");
    }
  });

  el("attachmentUrlInput")?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      addAttachmentFromUrl();
    }
  });

  const sessionInput = el("sessionId");
  if (sessionInput) {
    const commit = () => applySessionId(sessionInput.value, { persist: true, reflectCurrent: false });
    sessionInput.addEventListener("change", commit);
    sessionInput.addEventListener("blur", commit);
  }

  el("textInput")?.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendTextMessage();
    }
  });

  window.addEventListener("beforeunload", () => {
    if (state.ws && state.ws.readyState === WebSocket.OPEN) state.ws.close();
    stopPlaybackQueue();
  });
}

function init() {
  initTabs();
  wireButtons();
  applySessionId(localStorage.getItem(SESSION_STORAGE_KEY) || "default", { persist: false, reflectCurrent: true });
  updateConnectButton();
  updateMicButton();
  updateMuteButton();
  resetCallTimer();
  setPill("connState", "未连接", "muted");
  setPill("sessionState", "-", "muted");
  setSpeakerState("等待回复", "muted");
  setText("partial", "", "等待实时识别...");
  setText("final", "", "等待最终转写...");
  renderTimeline({});
  updateAttachmentState();
  flushPartialDraft();
  initRouterTestPanel();
  log("演示界面已就绪，点击「连接会话」开始。");
}

init();