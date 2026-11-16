import { el } from "./dom.js";
import { setText } from "./utils.js";
import { log } from "./log.js";

function pretty(value) {
  if (value === undefined || value === null || value === "") return "-";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

async function loadContract() {
  try {
    const resp = await fetch("/api/router/contract");
    const data = await resp.json();
    const lines = [
      `意图路由启用: ${data.intent_enabled} · provider: ${data.provider}`,
      `端侧模型: ${data.edge_model}`,
      `端侧地址: ${data.edge_api_base}`,
      `云兜底: ${data.cloud_fallback_enabled} · 最低置信: ${data.min_confidence}`,
      `路由模型: ${data.router_model} · 主干模型: ${data.responder_model}`,
    ];
    setText("rtContract", lines.join("\n"), "无");
  } catch (error) {
    setText("rtContract", `契约加载失败：${String(error?.message || error)}`);
  }
}

function renderResult(data) {
  if (!data || data.ok === false) {
    setText("rtMeta", `失败：${data?.error || "未知错误"}`);
    setText("rtClassification", "-");
    setText("rtPlanning", "-");
    setText("rtRaw", data?.raw_output || "-");
    return;
  }
  const meta = [];
  if (data.provider) meta.push(`provider ${data.provider}`);
  if (data.model) meta.push(`model ${data.model}`);
  if (data.latency_ms !== undefined) meta.push(`链路 ${Math.round(data.latency_ms)}ms`);
  if (data.first_token_ms !== undefined && data.first_token_ms !== null) meta.push(`首 token ${Math.round(data.first_token_ms)}ms`);
  if (data.total_ms !== undefined) meta.push(`总 ${Math.round(data.total_ms)}ms`);
  if (data.cache_hit) meta.push("缓存命中");
  if (data.view) meta.push(`视图 ${data.view}`);
  setText("rtMeta", meta.join(" · ") || "完成", "完成");
  setText("rtClassification", pretty(data.classification));
  setText("rtPlanning", pretty(data.planning));
  setText("rtRaw", data.raw_output || pretty(data.parsed) || "-");
}

async function runTest() {
  const text = el("rtText")?.value?.trim() || "";
  const image_url = el("rtImageUrl")?.value?.trim() || "";
  const target = el("rtTarget")?.value || "production";
  const mode = el("rtMode")?.value || "full";
  if (!text && !image_url) {
    setText("rtMeta", "请输入文本或图片 URL。");
    return;
  }
  const button = el("btnRunRouterTest");
  if (button) {
    button.disabled = true;
    button.textContent = "运行中...";
  }
  setText("rtMeta", "请求中（端侧 CPU 推理可能较慢，请稍候）...");
  try {
    const endpoint = target === "edge" ? "/api/router/edge" : "/api/router/test";
    const body = target === "edge" ? { text, image_url } : { text, image_url, mode };
    const resp = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await resp.json();
    renderResult(data);
    log(`路由测试（${target}/${mode}）：${data.ok === false ? "失败" : "完成"}`, data.ok === false ? "error" : "ok");
  } catch (error) {
    setText("rtMeta", `请求失败：${String(error?.message || error)}`);
    log(`路由测试请求失败：${String(error?.message || error)}`, "error");
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = "运行测试";
    }
  }
}

export function initRouterTestPanel() {
  el("btnRunRouterTest")?.addEventListener("click", runTest);
  el("rtText")?.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      runTest();
    }
  });
  loadContract();
}