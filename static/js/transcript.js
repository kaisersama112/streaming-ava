import { el } from "./dom.js";
import { state } from "./store.js";
import { compactValue, formatMessageTime, setSpeakerState } from "./utils.js";

// 打断且未产出 token 的轮次正文占位；.interrupted 的 ::after 会再追加「…[已打断]」。
const INTERRUPTED_EMPTY_TEXT = "（无输出）";

function isEmptyAssistantText(text) {
  return !text || text === "无";
}

function normalizeContent(content = []) {
  return Array.isArray(content) ? content.filter((block) => block && typeof block === "object") : [];
}

export function contentBlocksToDisplayText(content = []) {
  const lines = [];
  normalizeContent(content).forEach((block, index) => {
    const blockType = String(block.type || "").trim();
    if (blockType === "input_text" || blockType === "output_text") {
      const text = String(block.text || "").trim();
      if (text) lines.push(text);
    } else if (blockType === "input_image") {
      lines.push(`[图片] image-${index + 1}`);
    } else if (blockType === "input_audio") {
      lines.push(`[音频] audio-${index + 1}`);
    } else if (blockType === "input_file") {
      lines.push(`[文件] ${String(block.filename || `file-${index + 1}`).trim()}`);
    }
  });
  return lines.join("\n").trim() || "无";
}

export function extractAttachmentsFromContent(content = []) {
  const attachments = [];
  normalizeContent(content).forEach((block, index) => {
    const blockType = String(block.type || "").trim();
    if (blockType === "input_image") {
      const imageUrl = String(block.image_url || "").trim();
      attachments.push({
        name: `image-${index + 1}`,
        mime_type: "image/*",
        uri: imageUrl && !imageUrl.startsWith("data:") ? imageUrl : "",
        data_url: imageUrl.startsWith("data:") ? imageUrl : "",
        preview_url: imageUrl,
      });
    } else if (blockType === "input_audio") {
      const payload = block.input_audio || {};
      const audioData = String(payload.data || "").trim();
      const audioFormat = String(payload.format || "wav").trim();
      attachments.push({
        name: `audio-${index + 1}`,
        mime_type: `audio/${audioFormat}`,
        data_url: audioData,
        preview_url: audioData,
      });
    } else if (blockType === "input_file") {
      attachments.push({
        name: String(block.filename || `file-${index + 1}`).trim(),
        mime_type: String(block.mime_type || "").trim(),
        uri: String(block.file_url || block.uri || "").trim(),
        data_url: String(block.file_data || "").trim(),
        preview_url: String(block.file_url || block.uri || block.file_data || "").trim(),
      });
    }
  });
  return attachments;
}

export function userMessageToDisplayText(message = {}) {
  return contentBlocksToDisplayText(normalizeContent(message.content || []));
}

export function userMessageToAttachments(message = {}) {
  return extractAttachmentsFromContent(normalizeContent(message.content || []));
}

export function normalizeUserMessageContent(content = []) {
  return normalizeContent(content);
}

function describeAttachment(file) {
  const mime = file.mime_type || "";
  if (mime.startsWith("image/")) return "图片";
  if (mime.startsWith("audio/")) return "音频";
  if (mime.startsWith("video/")) return "视频";
  return "文件";
}

export function attachmentSummary(attachments = []) {
  return attachments.map((item) => `[${describeAttachment(item)}] ${item.name}`).join("\n");
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
    let media = null;
    if (mimeType.startsWith("image/")) {
      media = document.createElement("img");
      media.alt = item.name || "image";
    } else if (mimeType.startsWith("audio/")) {
      media = document.createElement("audio");
      media.controls = true;
      media.preload = "metadata";
    } else if (mimeType.startsWith("video/")) {
      media = document.createElement("video");
      media.controls = true;
      media.preload = "metadata";
    }
    if (!media) continue;
    media.src = src;
    preview.appendChild(media);
    container.appendChild(preview);
  }
}

function renderMessageMeta(container, meta = {}) {
  if (!container) return;
  container.innerHTML = "";
  const items = [
    ["scene", meta.turn_scene],
    ["task", meta.task],
    ["knowledge", meta.knowledge],
    ["follow-up", meta.user_followup_type],
  ];
  let count = 0;
  for (const [label, value] of items) {
    const text = String(value || "").trim();
    if (!text) continue;
    const chip = document.createElement("span");
    chip.className = "message-chip";
    const strong = document.createElement("strong");
    strong.textContent = label;
    const span = document.createElement("span");
    span.textContent = text;
    chip.append(strong, span);
    container.appendChild(chip);
    count += 1;
  }
  container.hidden = count === 0;
}

export function updateHistoryPanelSummary() {
  const transcript = el("transcript");
  if (!transcript) return;
  const nodes = [...transcript.querySelectorAll(".message")].filter(
    (node) => node.dataset.key !== "partial-draft"
  );
  const messageCount = el("historyMessageCount");
  if (messageCount) messageCount.textContent = String(nodes.length);
  const turnCount = el("historyTurnCount");
  if (turnCount) {
    turnCount.textContent = String(nodes.filter((node) => node.classList.contains("assistant")).length);
  }
  const focus = el("historyFocus");
  if (focus) {
    focus.textContent = compactValue(
      state.lastProfile.task || state.lastProfile.knowledge || state.lastProfile.capability
    );
  }
}

function scrollTranscriptToBottom() {
  const transcript = el("transcript");
  if (transcript) transcript.scrollTop = transcript.scrollHeight;
}

function createMessageNode(role, key, text = "", attachments = [], meta = null, timestamp = null, contentBlocks = []) {
  const article = document.createElement("article");
  article.className = `message ${role}`;
  article.dataset.key = key;

  const head = document.createElement("div");
  head.className = "message-head";
  const roleEl = document.createElement("div");
  roleEl.className = "message-role";
  roleEl.textContent = role === "user" ? "User" : role === "assistant" ? "AVA" : "System";
  const timeEl = document.createElement("div");
  timeEl.className = "message-time";
  timeEl.textContent = formatMessageTime(timestamp);
  head.append(roleEl, timeEl);
  article.appendChild(head);

  const mergedAttachments = attachments.length ? attachments : extractAttachmentsFromContent(contentBlocks);
  if (mergedAttachments.length) {
    const attachmentBlock = document.createElement("div");
    attachmentBlock.className = "message-text message-attachments";
    attachmentBlock.textContent = attachmentSummary(mergedAttachments);
    article.appendChild(attachmentBlock);
    appendAttachmentPreviews(article, mergedAttachments);
  }

  const textEl = document.createElement("div");
  textEl.className = "message-text";
  textEl.textContent = text || contentBlocksToDisplayText(contentBlocks);
  article.appendChild(textEl);

  const metaEl = document.createElement("div");
  metaEl.className = "message-meta";
  metaEl.hidden = true;
  article.appendChild(metaEl);
  if (meta) {
    state.messageMetaStore.set(key, { ...(state.messageMetaStore.get(key) || {}), ...meta });
    renderMessageMeta(metaEl, state.messageMetaStore.get(key));
  }

  el("transcript").appendChild(article);
  scrollTranscriptToBottom();
  updateHistoryPanelSummary();
  return article;
}

function getMessageTextEl(node) {
  if (!node) return null;
  const blocks = node.querySelectorAll(".message-text:not(.message-attachments)");
  return blocks.length ? blocks[blocks.length - 1] : null;
}

export function addMessage(role, text, options = {}) {
  const key = options.key || `${role}-${Date.now()}-${state.localMessageSeq++}`;
  if (role === "user") {
    if (state.userMessageKeys.has(key)) return key;
    state.userMessageKeys.add(key);
  }
  const node = createMessageNode(
    role,
    key,
    text,
    options.attachments || [],
    options.meta || null,
    options.timestamp || Date.now(),
    options.contentBlocks || []
  );
  if (options.interrupted) node.classList.add("interrupted");
  if (role === "assistant" && options.interrupted) {
    const textEl = getMessageTextEl(node);
    if (textEl && isEmptyAssistantText(textEl.textContent)) textEl.textContent = INTERRUPTED_EMPTY_TEXT;
  }
  if (role === "assistant") state.assistantNodes.set(key, node);
  return key;
}

export function ensureAssistantMessage(turnId) {
  const key = String(turnId || `assistant-${Date.now()}`);
  let node = state.assistantNodes.get(key);
  if (!node) {
    node = createMessageNode("assistant", key, "", [], state.messageMetaStore.get(key) || null, Date.now());
    state.assistantNodes.set(key, node);
    const textEl = getMessageTextEl(node);
    if (textEl && textEl.textContent === "无") textEl.textContent = "";
    node.classList.add("streaming");
  }
  state.activeAssistantTurnId = key;
  return node;
}

export function setMessageMeta(key, patch = {}) {
  const normalizedKey = String(key || "");
  if (!normalizedKey) return;
  const merged = { ...(state.messageMetaStore.get(normalizedKey) || {}), ...patch };
  state.messageMetaStore.set(normalizedKey, merged);
  const node = el("transcript")?.querySelector(`[data-key="${CSS.escape(normalizedKey)}"]`);
  if (!node) return;
  renderMessageMeta(node.querySelector(".message-meta"), merged);
  updateHistoryPanelSummary();
}

export function appendAssistantToken(turnId, token) {
  const node = ensureAssistantMessage(turnId);
  const textEl = getMessageTextEl(node);
  if (!textEl) return;
  if (textEl.textContent === "无") textEl.textContent = "";
  textEl.textContent += token || "";
  node.classList.add("streaming");
  scrollTranscriptToBottom();
}

export function finishAssistant(turnId, interrupted = false, assistantMessage = null) {
  const key = String(turnId || state.activeAssistantTurnId || "");
  if (!key) return;
  const node = ensureAssistantMessage(key);
  node.classList.remove("streaming");
  const textEl = getMessageTextEl(node);
  const text = contentBlocksToDisplayText(normalizeContent((assistantMessage || {}).content || []));
  if (textEl && (!textEl.textContent || textEl.textContent === "无") && text && text !== "无") {
    textEl.textContent = text;
  }
  if (interrupted) {
    node.classList.add("interrupted");
    if (textEl && isEmptyAssistantText(textEl.textContent)) textEl.textContent = INTERRUPTED_EMPTY_TEXT;
  }
  state.activeAssistantTurnId = null;
  setSpeakerState(interrupted ? "已打断" : "回复完成", interrupted ? "warn" : "ok");
}

export function upsertPartialDraft(userMessage = null) {
  const clean = userMessageToDisplayText(userMessage || {});
  if (!clean || clean === "无") {
    flushPartialDraft();
    return;
  }
  if (!state.partialDraftId) {
    state.partialDraftId = addMessage("user", clean, { key: "partial-draft" });
    const node = el("transcript")?.querySelector('[data-key="partial-draft"]');
    if (node) node.classList.add("partial");
  } else {
    const node = el("transcript")?.querySelector(`[data-key="${CSS.escape(state.partialDraftId)}"]`);
    const textEl = getMessageTextEl(node);
    if (textEl) textEl.textContent = clean;
  }
  scrollTranscriptToBottom();
}

export function flushPartialDraft() {
  if (!state.partialDraftId) return;
  const node = el("transcript")?.querySelector(`[data-key="${CSS.escape(state.partialDraftId)}"]`);
  if (node) node.remove();
  state.partialDraftId = null;
}

export function clearTranscript() {
  state.assistantNodes.clear();
  state.userMessageKeys.clear();
  state.messageMetaStore.clear();
  state.interruptedAssistantTurns.clear();
  state.activeAssistantTurnId = null;
  state.partialDraftId = null;
  const transcript = el("transcript");
  if (transcript) transcript.innerHTML = "";
  updateHistoryPanelSummary();
}