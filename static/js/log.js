import { el } from "./dom.js";
import { MAX_LOG_ENTRIES } from "./config.js";

const LEVEL_CLASS = { info: "log-info", ok: "log-ok", warn: "log-warn", error: "log-error" };

export function log(line, level = "info") {
  const container = el("log");
  if (!container) return;
  const entry = document.createElement("div");
  entry.className = `log-entry ${LEVEL_CLASS[level] || LEVEL_CLASS.info}`;
  const ts = document.createElement("span");
  ts.className = "log-ts";
  ts.textContent = new Date().toISOString().slice(11, 19);
  const body = document.createElement("span");
  body.className = "log-body";
  body.textContent = String(line ?? "");
  entry.append(ts, body);
  container.prepend(entry);
  while (container.childElementCount > MAX_LOG_ENTRIES) {
    container.lastElementChild.remove();
  }
}

export function clearLog() {
  const container = el("log");
  if (container) container.innerHTML = "";
}