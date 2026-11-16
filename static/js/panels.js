import { el } from "./dom.js";
import { state } from "./store.js";
import { TIMELINE_LABELS } from "./config.js";
import { formatLatency, formatSkillList, normalizeSkillNames, setPill, setText } from "./utils.js";
import { log } from "./log.js";

export function applyPromptProfile(profile = {}) {
  state.lastProfile = { ...state.lastProfile, ...profile };
  setText("currentCapability", profile.capability);
  setText("currentTask", profile.task);
  setText("currentKnowledge", profile.knowledge);
  setText("currentMethod", profile.method);
  setText("currentAudience", profile.audience);
  setText("currentSkills", formatSkillList(profile.skills || []));
}

export function renderRouteMeta(msg) {
  state.lastRoute = {
    turn_scene: msg.turn_scene || "",
    session_scene: msg.session_scene || "",
    confidence: msg.confidence,
    handler: msg.handler || "",
  };
  setText("currentRoute", `${msg.turn_scene || "-"} / ${msg.session_scene || "-"}`);
  setText("currentHandler", msg.handler);
  const confidenceEl = el("routeConfidence");
  if (confidenceEl) {
    const confidence = Number(msg.confidence);
    if (Number.isFinite(confidence)) {
      confidenceEl.textContent = confidence.toFixed(2);
      confidenceEl.className = `confidence-badge ${confidence >= 0.8 ? "high" : confidence >= 0.5 ? "mid" : "low"}`;
    } else {
      confidenceEl.textContent = "-";
      confidenceEl.className = "confidence-badge";
    }
  }
}

export function renderHelloMeta(latestMeta = {}) {
  setText("currentRoute", `${latestMeta.turn_scene || "-"} / ${latestMeta.session_scene || "-"}`);
  applyPromptProfile(latestMeta);
  setText("currentFollowupType", latestMeta.user_followup_type);
  setText("currentPromptSource", latestMeta.prompt_source);
}

export function renderPromptPackage(msg) {
  applyPromptProfile(msg.prompt_profile || {});
  setText("currentFollowupType", msg.user_followup_type);
  setText("currentPromptSource", msg.prompt_source);
  setText("artifactTextView", JSON.stringify(msg.analysis || {}, null, 2), "{}");
}

export function renderDebugContext(msg) {
  setText("multimodalSummary", JSON.stringify((msg.user_message || {}).content || [], null, 2), "[]");
}

export function renderDebugPrompt(msg) {
  setText("currentHandler", msg.handler);
  applyPromptProfile(msg.prompt_profile || {});
  setText("currentSkills", formatSkillList(msg.active_skills || (msg.prompt_profile || {}).skills || []));
  setText("promptView", msg.system_prompt, "无");
}

export function renderTimeline(timeline = {}) {
  state.lastTimeline = { ...timeline };
  const container = el("timelineView");
  if (!container) return;
  container.innerHTML = "";
  const values = TIMELINE_LABELS.map(([key]) => Number(timeline[key])).filter(Number.isFinite);
  const max = Math.max(1, ...values);
  let any = false;
  for (const [key, label] of TIMELINE_LABELS) {
    const value = Number(timeline[key]);
    const row = document.createElement("div");
    row.className = "timeline-row";
    const labelEl = document.createElement("span");
    labelEl.className = "timeline-label";
    labelEl.textContent = label;
    const track = document.createElement("div");
    track.className = "timeline-track";
    const valueEl = document.createElement("span");
    valueEl.className = "timeline-value";
    if (Number.isFinite(value)) {
      any = true;
      const fill = document.createElement("div");
      fill.className = "timeline-fill";
      fill.style.width = `${Math.max(2, (value / max) * 100)}%`;
      track.appendChild(fill);
      valueEl.textContent = `${Math.round(value)}ms`;
    } else {
      valueEl.textContent = "-";
    }
    row.append(labelEl, track, valueEl);
    container.appendChild(row);
  }
  if (!any) container.dataset.empty = "true";
  else delete container.dataset.empty;
}

export function renderMetrics(msg) {
  setText("metricAsrFinalLatency", formatLatency(msg.asr_final_latency_ms));
  setText("metricFirstTokenLatency", formatLatency(msg.first_token_latency_ms));
  setText("metricFirstAudioLatency", formatLatency(msg.first_audio_latency_ms));
  setText("metricInterruptCount", String(Number(msg.interrupt_count || 0)), "0");
  renderTimeline(msg.timeline_ms || {});
}

function renderOrchestration(orchestration = {}) {
  const container = el("orchestrationView");
  if (!container) return;
  container.innerHTML = "";
  const results = Array.isArray(orchestration.results) ? orchestration.results : [];
  if (!results.length) {
    container.textContent = "无（单模型直答）";
    return;
  }
  const head = document.createElement("div");
  head.className = "orchestration-head";
  head.textContent = `模式 ${orchestration.mode || "-"} · 总耗时 ${Math.round(Number(orchestration.latency_ms || 0))}ms`;
  container.appendChild(head);
  for (const item of results) {
    const row = document.createElement("div");
    row.className = "orchestration-row";
    const skill = document.createElement("span");
    skill.className = "orchestration-skill";
    skill.textContent = item.skill || item.task_id || "?";
    const status = document.createElement("span");
    const statusText = String(item.status || "ok");
    status.className = `status-chip ${statusText === "ok" ? "ok" : statusText === "cancelled" ? "warn" : "error"}`;
    status.textContent = statusText;
    const latency = document.createElement("span");
    latency.className = "orchestration-latency";
    latency.textContent = `${Math.round(Number(item.latency_ms || 0))}ms`;
    row.append(skill, status, latency);
    if (item.error) {
      const error = document.createElement("div");
      error.className = "orchestration-error";
      error.textContent = String(item.error);
      row.appendChild(error);
    }
    container.appendChild(row);
  }
}

function renderStatePatches(applied = [], rejected = []) {
  const container = el("statePatchView");
  if (!container) return;
  container.innerHTML = "";
  if (!applied.length && !rejected.length) {
    container.textContent = "无";
    return;
  }
  for (const patch of applied) {
    const row = document.createElement("div");
    row.className = "patch-row applied";
    row.textContent = `✓ ${patch.key} = ${JSON.stringify(patch.value)}${patch.actor ? `（${patch.actor}）` : ""}`;
    container.appendChild(row);
  }
  for (const patch of rejected) {
    const row = document.createElement("div");
    row.className = "patch-row rejected";
    row.textContent = `✗ ${patch.key} 拒绝：${patch.reject_reason || patch.reason || "not_in_whitelist"}`;
    container.appendChild(row);
  }
}

function renderAgentEvents(events = []) {
  const container = el("agentEventsView");
  if (!container) return;
  container.innerHTML = "";
  if (!events.length) {
    container.textContent = "无";
    return;
  }
  for (const item of events.slice(0, 40)) {
    const row = document.createElement("div");
    row.className = "agent-event-row";
    if (typeof item === "string") {
      row.textContent = item;
    } else {
      const name = item.event || item.type || "event";
      const detail = item.detail || item.message || item.tool || "";
      row.textContent = `${name}${detail ? ` · ${typeof detail === "string" ? detail : JSON.stringify(detail)}` : ""}`;
    }
    container.appendChild(row);
  }
}

export function renderPipelineDebug(msg) {
  state.lastPipelineDebug = msg;
  const selection = msg.model_selection || {};
  const backend = msg.backend || "-";
  setText(
    "modelSelectionView",
    selection.model
      ? `${backend} · ${selection.tier || "primary"} · ${selection.model}${selection.reason ? `（${selection.reason}）` : ""}`
      : backend
  );

  const orchestration = msg.orchestration || {};
  const results = Array.isArray(orchestration.results) ? orchestration.results : [];
  const applied = Array.isArray(msg.applied_state_patches) ? msg.applied_state_patches : [];
  const rejected = Array.isArray(msg.rejected_state_patches) ? msg.rejected_state_patches : [];
  renderOrchestration(orchestration);
  renderStatePatches(applied, rejected);
  renderAgentEvents(Array.isArray(msg.agent_debug_events) ? msg.agent_debug_events : []);

  const patchBadge = el("tabBadgeState");
  if (patchBadge) {
    const total = applied.length + rejected.length;
    patchBadge.textContent = total ? String(total) : "";
    patchBadge.hidden = !total;
  }
  if (results.length || applied.length || rejected.length) {
    log(`链路调试：${backend} · 技能 ${results.length} · patch 应用 ${applied.length} / 拒绝 ${rejected.length}`);
  }
}

export function renderSessionState(sessionState) {
  const className =
    sessionState === "speaking" ? "ok" :
    sessionState === "interrupting" ? "warn" :
    sessionState === "thinking" ? "warn" :
    sessionState === "shutdown" ? "danger" :
    "muted";
  setPill("sessionState", sessionState || "-", className);
}

export function buildDebugContextText() {
  const profile = state.lastProfile || {};
  const route = state.lastRoute || {};
  const attachmentLines = state.pendingAttachments.length
    ? state.pendingAttachments.map((item) => `- ${item.name}`).join("\n")
    : "无";
  const timelineText = TIMELINE_LABELS.map(([key, label]) => {
    const value = Number(state.lastTimeline[key]);
    return `${label}: ${Number.isFinite(value) ? `${Math.round(value)}ms` : "-"}`;
  }).join("\n");
  return [
    `路由: ${route.turn_scene || "-"} / ${route.session_scene || "-"}（置信度 ${route.confidence ?? "-"}）`,
    `处理器: ${route.handler || "-"}`,
    `能力: ${profile.capability || "-"}`,
    `任务: ${profile.task || "-"}`,
    `知识: ${profile.knowledge || "-"}`,
    `方法: ${profile.method || "-"}`,
    `受众: ${profile.audience || "-"}`,
    `技能: ${formatSkillList(profile.skills || [])}`,
    "",
    "附件：",
    attachmentLines,
    "",
    "多模态摘要：",
    el("multimodalSummary")?.textContent || "无",
    "",
    "附件分析：",
    el("artifactTextView")?.textContent || "无",
    "",
    "系统提示词：",
    el("promptView")?.textContent || "无",
    "",
    "轮次时序：",
    timelineText,
  ].join("\n");
}