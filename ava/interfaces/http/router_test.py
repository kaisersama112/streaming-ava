"""路由能力独立测试接口。

提供两个端点：
- POST /api/router/test  走生产链路（RouterService.prepare_turn：端侧小模型优先 + 云兜底 + 规划），
  按 mode 返回 意图识别(full) / 分类(classify) / 规划(plan) 视图。
- POST /api/router/edge  直测本地部署的剪枝+INT8 视觉小模型（OpenAI 兼容 :8080），
  使用与 SFT 数据集一致的路由 JSON 契约，返回原始输出、解析结果、首 token 与总延迟。

两者均支持文本 + 图片（data: / http(s) / 本地路径）多模态输入。
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/router", tags=["router-test"])

_ROOT = Path(__file__).resolve().parents[3]
_SFT_FILE = _ROOT / "data" / "router_sft_train.jsonl"


class RouterTestRequest(BaseModel):
    text: str = ""
    image_url: str = ""
    mode: str = "full"  # full | classify | plan
    prior_scene: str = ""  # 可选：预置会话主场景 education/general


class EdgeTestRequest(BaseModel):
    text: str = ""
    image_url: str = ""
    max_tokens: int = 256


def _router_system_prompt() -> str:
    try:
        text = _SFT_FILE.read_text(encoding="utf-8").strip()
        obj, _ = json.JSONDecoder().raw_decode(text)
        recs = obj if isinstance(obj, list) else [obj]
        for msg in recs[0].get("messages", []):
            if msg.get("role") == "system":
                return str(msg.get("content", ""))
    except Exception:
        pass
    return "你是路由分类器。只输出一个 JSON 对象。"


def _content_blocks(text: str, image_url: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    if text.strip():
        blocks.append({"type": "input_text", "text": text.strip()})
    if image_url.strip():
        blocks.append({"type": "input_image", "image_url": image_url.strip()})
    return blocks


def _run_production(req: RouterTestRequest) -> dict[str, Any]:
    from configs import settings
    from ava.capabilities.prompt import build_prompt_center
    from ava.core.tracing import new_trace_id
    from ava.domain.conversation.state import ConversationState
    from ava.domain.multimodal.continuity import artifact_blocks, blocks_to_artifacts
    from ava.domain.multimodal.edge_vision import ensure_visual_analysis
    from ava.multi_turn_context_builder import ContextCompiler
    from ava.router_selector import RouterService

    blocks = _content_blocks(req.text, req.image_url)
    if not blocks:
        return {"ok": False, "error": "empty input"}

    user_message = {"role": "user", "content": blocks}
    state = ConversationState(
        settings.runtime.state_file,
        settings.runtime.history_window,
        session_id=f"router-test-{uuid.uuid4().hex[:10]}",
    )
    if req.prior_scene in {"education", "general"}:
        state.session_scene = req.prior_scene

    if req.image_url.strip():
        ensure_visual_analysis(state.memory, blocks_to_artifacts(artifact_blocks(user_message)))

    service = RouterService(prompt_center=build_prompt_center(), context_compiler=ContextCompiler())
    trace_id = new_trace_id()
    started = time.monotonic()
    prepared = service.prepare_turn(
        prompt_center=service.prompt_center,
        state=state,
        user_message=user_message,
        history_window=settings.runtime.history_window,
        max_context_messages=int(getattr(settings.runtime, "router_max_context_messages", 0) or 0) or None,
        current_turn_id=1,
        router_model=settings.openai_config.router_model,
        responder_model=settings.openai_config.model,
        timeout=int(settings.openai_config.timeout),
        api_base=settings.openai_config.api_base,
        api_key=settings.openai_config.api_key,
        trace_id=trace_id,
    )
    latency_ms = round((time.monotonic() - started) * 1000, 2)
    route_result = prepared.route_result
    plan = prepared.turn_plan
    decision = route_result.decision
    classification = {
        "session_scene": decision.session_scene,
        "turn_scene": decision.turn_scene,
        "intent": decision.intent,
        "confidence": decision.confidence,
        "need_clarification": decision.need_clarification,
        "should_preserve_teaching_state": decision.should_preserve_teaching_state,
    }
    planning = {
        "router_plan": dict(route_result.router_plan or {}),
        "strategy_id": getattr(plan.strategy, "strategy_id", ""),
        "orchestrator": plan.execution.orchestrator_name,
        "active_skills": list(plan.debug.active_skills),
        "responder_model": plan.execution.model,
    }
    summary = dict(route_result.selection_summary or {})
    base = {
        "ok": True,
        "trace_id": trace_id,
        "latency_ms": latency_ms,
        "provider": summary.get("provider", ""),
        "model": summary.get("model", ""),
        "cache_hit": summary.get("cache_hit", False),
        "raw_output": route_result.raw_output,
        "classification": classification,
        "planning": planning,
    }
    mode = (req.mode or "full").strip().lower()
    if mode == "classify":
        base["view"] = "classify"
        base.pop("planning", None)
    elif mode == "plan":
        base["view"] = "plan"
        base.pop("classification", None)
    else:
        base["view"] = "full"
    return base


def _run_edge(req: EdgeTestRequest) -> dict[str, Any]:
    import httpx

    from configs import settings

    local = settings.intent_config.local
    api_base = str(local.api_base or "http://127.0.0.1:8080/v1").rstrip("/")
    content: list[dict[str, Any]] = [{"type": "text", "text": req.text.strip() or "请路由"}]
    if req.image_url.strip():
        content.append({"type": "image_url", "image_url": {"url": req.image_url.strip()}})
    messages = [
        {"role": "system", "content": _router_system_prompt()},
        {"role": "user", "content": content},
    ]
    payload = {
        "model": local.model,
        "messages": messages,
        "max_tokens": int(req.max_tokens),
        "stream": True,
        "temperature": 0,
    }
    started = time.monotonic()
    first_token_ms = None
    pieces: list[str] = []
    try:
        with httpx.Client(timeout=float(local.timeout_ms) / 1000.0 + 30, trust_env=False) as client:
            with client.stream("POST", f"{api_base}/chat/completions", json=payload) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    delta = (chunk.get("choices") or [{}])[0].get("delta", {})
                    piece = delta.get("content")
                    if piece:
                        if first_token_ms is None:
                            first_token_ms = round((time.monotonic() - started) * 1000, 2)
                        pieces.append(piece)
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}", "model": local.model, "api_base": api_base}

    total_ms = round((time.monotonic() - started) * 1000, 2)
    raw = "".join(pieces)
    parsed: dict[str, Any] = {}
    parse_error = ""
    try:
        text = raw.strip()
        start, end = text.find("{"), text.rfind("}")
        parsed = json.loads(text[start:end + 1]) if start != -1 and end > start else json.loads(text)
    except Exception as exc:
        parse_error = str(exc)
    if not isinstance(parsed, dict):
        parse_error = parse_error or f"non-object output: {type(parsed).__name__}"
        parsed = {}
    return {
        "ok": True,
        "model": local.model,
        "api_base": api_base,
        "first_token_ms": first_token_ms,
        "total_ms": total_ms,
        "raw_output": raw,
        "parsed": parsed,
        "parse_error": parse_error,
        "classification": {k: parsed.get(k) for k in ("session_scene", "turn_scene", "intent", "confidence")},
        "planning": parsed.get("plan", {}),
    }


@router.post("/test")
async def router_test(req: RouterTestRequest) -> dict[str, Any]:
    return await asyncio.to_thread(_run_production, req)


@router.post("/edge")
async def router_edge(req: EdgeTestRequest) -> dict[str, Any]:
    return await asyncio.to_thread(_run_edge, req)


@router.get("/contract")
async def router_contract() -> dict[str, Any]:
    from configs import settings

    local = settings.intent_config.local
    return {
        "system_prompt": _router_system_prompt(),
        "intent_enabled": bool(settings.intent_config.enabled),
        "provider": settings.intent_config.provider,
        "edge_model": local.model,
        "edge_api_base": local.api_base,
        "cloud_fallback_enabled": bool(settings.intent_config.cloud_fallback_enabled),
        "min_confidence": float(settings.intent_config.min_confidence),
        "responder_model": settings.openai_config.model,
        "router_model": settings.openai_config.router_model,
    }