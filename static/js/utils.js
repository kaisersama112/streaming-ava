import { el } from "./dom.js";

export function compactValue(value, fallback = "-") {
  const text = String(value ?? "").trim();
  return text && text !== "-" ? text : fallback;
}

export function setText(id, text, fallback = "-") {
  const target = el(id);
  if (!target) return;
  const value = String(text ?? "").trim();
  target.textContent = value ? value : fallback;
}

export function setPill(id, text, className = "muted") {
  const target = el(id);
  if (!target) return;
  target.textContent = text;
  target.className = `pill-value ${className}`;
}

export function setSpeakerState(text, className = "muted") {
  setPill("speakerState", text, className);
}

export function formatLatency(value) {
  const ms = Number(value);
  if (!Number.isFinite(ms)) return "-";
  return ms >= 1000 ? `${(ms / 1000).toFixed(2)}s` : `${Math.round(ms)}ms`;
}

export function formatBytes(bytes) {
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

export function formatMessageTime(value) {
  const date = value ? new Date(value) : new Date();
  if (Number.isNaN(date.getTime())) return "--:--";
  return date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
}

export function formatElapsed(ms) {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

export function normalizeSkillNames(skills = []) {
  if (!Array.isArray(skills)) return [];
  return skills.map((item) => String(item || "").trim()).filter(Boolean);
}

export function formatSkillList(skills = []) {
  const items = normalizeSkillNames(skills);
  return items.length ? items.join(" / ") : "-";
}

export function normalizeSessionId(value) {
  const normalized = String(value || "")
    .trim()
    .replace(/[^\w\-.:]/g, "_")
    .slice(0, 64);
  return normalized || "default";
}

export function dataUrlToBase64(dataUrl) {
  const idx = String(dataUrl || "").indexOf(",");
  return idx >= 0 ? dataUrl.slice(idx + 1) : String(dataUrl || "");
}

export function inlineSourceToBase64(source) {
  return typeof source === "string" && source.startsWith("data:") ? dataUrlToBase64(source) : "";
}