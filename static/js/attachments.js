import { el } from "./dom.js";
import { state } from "./store.js";
import { dataUrlToBase64, formatBytes, inlineSourceToBase64 } from "./utils.js";
import { log } from "./log.js";

function describeAttachment(file) {
  const mime = file.mime_type || "";
  if (mime.startsWith("image/")) return "图片";
  if (mime.startsWith("audio/")) return "音频";
  if (mime.startsWith("video/")) return "视频";
  return "文件";
}

function getPreviewSource(item) {
  const candidate = item.preview_url || item.data_url || item.uri || "";
  return typeof candidate === "string" ? candidate : "";
}

export function updateAttachmentState() {
  const target = el("stagedAttachmentState");
  if (!target) return;
  if (!state.pendingAttachments.length) {
    target.textContent = "未选择附件。";
    return;
  }
  const isOpen = !!state.ws && state.ws.readyState === WebSocket.OPEN;
  target.textContent = isOpen
    ? `已选择 ${state.pendingAttachments.length} 个附件，并已同步到当前会话。后续文本与语音提问都会持续带上它们，直到手动移除。`
    : `已选择 ${state.pendingAttachments.length} 个附件，当前仅保存在本地。建立连接后会自动同步到会话。`;
}

export function buildAttachmentPayload() {
  return state.pendingAttachments.map((item) => ({
    name: item.name,
    mime_type: item.mime_type,
    data_base64: item.data_base64 || inlineSourceToBase64(getPreviewSource(item)),
    uri: item.uri || "",
  }));
}

export function syncStagedAttachments() {
  if (!state.ws || state.ws.readyState !== WebSocket.OPEN) {
    updateAttachmentState();
    return;
  }
  const payload = buildAttachmentPayload();
  state.ws.send(
    JSON.stringify(
      payload.length
        ? { type: "stage_attachments", attachments: payload }
        : { type: "clear_staged_attachments" }
    )
  );
  updateAttachmentState();
}

function appendPreview(wrapper, item) {
  const src = getPreviewSource(item);
  if (!src) return;
  const mime = String(item.mime_type || "");
  let media = null;
  if (mime.startsWith("image/")) {
    media = document.createElement("img");
    media.alt = item.name || "image";
  } else if (mime.startsWith("audio/")) {
    media = document.createElement("audio");
    media.controls = true;
    media.preload = "metadata";
  } else if (mime.startsWith("video/")) {
    media = document.createElement("video");
    media.controls = true;
    media.preload = "metadata";
  }
  if (!media) return;
  media.src = src;
  const preview = document.createElement("div");
  preview.className = "attachment-preview";
  preview.appendChild(media);
  wrapper.appendChild(preview);
}

export function renderAttachmentList() {
  const list = el("attachmentList");
  if (!list) return;
  list.innerHTML = "";
  state.pendingAttachments.forEach((item, index) => {
    const wrapper = document.createElement("div");
    wrapper.className = "attachment-item";

    const head = document.createElement("div");
    head.className = "attachment-head";
    const meta = document.createElement("div");
    meta.className = "attachment-meta";
    const name = document.createElement("span");
    name.className = "attachment-name";
    name.textContent = item.name;
    const desc = document.createElement("span");
    desc.className = "attachment-desc";
    desc.textContent = `${describeAttachment(item)} · ${item.uri ? "URL" : formatBytes(item.size_bytes)}`;
    meta.append(name, desc);
    head.appendChild(meta);

    const removeBtn = document.createElement("button");
    removeBtn.className = "btn btn-ghost btn-sm";
    removeBtn.type = "button";
    removeBtn.textContent = "移除";
    removeBtn.addEventListener("click", () => {
      state.pendingAttachments.splice(index, 1);
      renderAttachmentList();
      syncStagedAttachments();
    });
    head.appendChild(removeBtn);
    wrapper.appendChild(head);
    appendPreview(wrapper, item);

    if (item.uri) {
      const source = document.createElement("a");
      source.className = "attachment-uri";
      source.href = item.uri;
      source.target = "_blank";
      source.rel = "noreferrer noopener";
      source.textContent = item.uri;
      wrapper.appendChild(source);
    }
    list.appendChild(wrapper);
  });
  updateAttachmentState();
}

export function hydrateFromServer(attachments = []) {
  state.pendingAttachments = attachments.map((item) => ({
    ...item,
    preview_url: getPreviewSource(item),
    data_base64: inlineSourceToBase64(getPreviewSource(item)),
    size_bytes: Number(item.size_bytes || 0),
  }));
  renderAttachmentList();
}

export function clearAttachments({ sync = true } = {}) {
  state.pendingAttachments = [];
  const fileInput = el("attachmentInput");
  if (fileInput) fileInput.value = "";
  const urlInput = el("attachmentUrlInput");
  if (urlInput) urlInput.value = "";
  renderAttachmentList();
  if (sync) syncStagedAttachments();
}

function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(reader.error || new Error("read file failed"));
    reader.readAsDataURL(file);
  });
}

export async function handleAttachmentSelection(files) {
  for (const file of Array.from(files || [])) {
    const dataUrl = await readFileAsDataUrl(file);
    state.pendingAttachments.push({
      name: file.name,
      mime_type: file.type || "application/octet-stream",
      size_bytes: file.size,
      data_base64: dataUrlToBase64(dataUrl),
      preview_url: dataUrl,
    });
  }
  renderAttachmentList();
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
  parsed.pathname = parsed.pathname
    .split("/")
    .map((segment) => {
      try {
        return encodeURIComponent(decodeURIComponent(segment));
      } catch {
        return encodeURIComponent(segment);
      }
    })
    .join("/");
  return parsed.toString();
}

function guessMimeTypeFromUrl(url) {
  let pathname = "";
  try {
    pathname = new URL(url).pathname.toLowerCase();
  } catch {}
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
    const segments = new URL(url).pathname.split("/").filter(Boolean);
    const name = segments[segments.length - 1];
    if (name) return decodeURIComponent(name);
  } catch {}
  if (mimeType.startsWith("image/")) return "remote-image";
  if (mimeType.startsWith("audio/")) return "remote-audio";
  if (mimeType.startsWith("video/")) return "remote-video";
  return "remote-attachment";
}

export function addAttachmentFromUrl() {
  const input = el("attachmentUrlInput");
  const normalized = normalizeAttachmentUrl(input?.value || "");
  if (!normalized) {
    log("附件链接无效", "warn");
    return;
  }
  const mimeType = guessMimeTypeFromUrl(normalized);
  state.pendingAttachments.push({
    name: guessNameFromUrl(normalized, mimeType),
    mime_type: mimeType,
    size_bytes: 0,
    uri: normalized,
    preview_url: normalized,
    data_base64: "",
  });
  if (input) input.value = "";
  renderAttachmentList();
  syncStagedAttachments();
  log(`附件链接已加入暂存：${normalized}`);
}