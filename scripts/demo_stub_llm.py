"""本地演示用 OpenAI 兼容桩服务（无云端密钥时的离线演示后端）。

仅用于演示与联调：
- POST /v1/responses        Router / LLMService 链路（含 SSE 流式）
- POST /v1/chat/completions Agents SDK Manager / 技能子 Agent 链路

路由按关键词给出确定性 RouteDecision；技能子 Agent 第一轮调用
note_state_patch 工具（含一条白名单外字段用于演示拒绝），第二轮输出文本。

启动: .venv/Scripts/python.exe scripts/demo_stub_llm.py [--port 8090]
"""

from __future__ import annotations

import argparse
import json
import re
import time
import uuid

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

app = FastAPI(title="demo-stub-llm")

_COUNTER = {"n": 0}


def _next_id(prefix: str) -> str:
    _COUNTER["n"] += 1
    return f"{prefix}_stub_{_COUNTER['n']:04d}_{uuid.uuid4().hex[:6]}"


def _last_user_text_from_responses(body: dict) -> str:
    for item in reversed(list(body.get("input") or [])):
        if str(item.get("role", "")) != "user":
            continue
        content = item.get("content")
        if isinstance(content, str):
            return content
        parts = []
        for block in list(content or []):
            if isinstance(block, dict) and block.get("type") == "input_text":
                parts.append(str(block.get("text", "")))
        if parts:
            return "\n".join(parts)
    return ""


def _route_decision(text: str) -> dict:
    secondary: list[str] = []
    if any(k in text for k in ("批改", "检查", "判一判", "对不对")):
        module = "check"
        if any(k in text for k in ("评估", "学情", "掌握")):
            secondary.append("assess")
    elif any(k in text for k in ("讲解", "为什么", "讲一下", "解释")):
        module = "explain"
    elif any(k in text for k in ("评估", "学情", "掌握情况")):
        module = "assess"
    elif any(k in text for k in ("解", "计算", "题", "方程", "等于")):
        module = "solve"
    else:
        return {
            "session_scene": "general",
            "turn_scene": "general_qa",
            "intent": "qa",
            "confidence": 0.92,
            "need_clarification": False,
            "should_preserve_teaching_state": False,
            "plan": {"module": "qa"},
        }
    plan: dict = {"module": module, "subject": "math"}
    if secondary:
        plan["secondary_actions"] = secondary
    return {
        "session_scene": "education",
        "turn_scene": "education",
        "intent": module,
        "confidence": 0.93,
        "need_clarification": False,
        "should_preserve_teaching_state": True,
        "plan": plan,
    }


def _responses_text(body: dict) -> str:
    instructions = str(body.get("instructions", "") or "")
    text = _last_user_text_from_responses(body)
    if "turn_scene" in instructions:
        return json.dumps(_route_decision(text), ensure_ascii=False)
    return f"【演示回复】收到：{text[:120]}。这是本地桩模型的演示回答，接入真实密钥后由云端模型生成。"


def _response_object(resp_id: str, model: str, text: str, status: str = "completed") -> dict:
    return {
        "id": resp_id,
        "object": "response",
        "created_at": int(time.time()),
        "status": status,
        "model": model,
        "output": [
            {
                "id": f"msg_{resp_id}",
                "type": "message",
                "role": "assistant",
                "status": status,
                "content": [{"type": "output_text", "text": text, "annotations": []}],
            }
        ],
        "usage": {"input_tokens": 32, "output_tokens": max(1, len(text) // 2), "total_tokens": 32 + len(text) // 2},
    }


@app.post("/v1/responses")
async def responses(request: Request):
    body = await request.json()
    model = str(body.get("model", "stub-model"))
    text = _responses_text(body)
    resp_id = _next_id("resp")
    if not body.get("stream"):
        return JSONResponse(_response_object(resp_id, model, text))

    async def _sse():
        created = _response_object(resp_id, model, "", status="in_progress")
        yield f"event: response.created\ndata: {json.dumps({'type': 'response.created', 'response': created}, ensure_ascii=False)}\n\n"
        for index in range(0, len(text), 16):
            delta = text[index: index + 16]
            event = {"type": "response.output_text.delta", "delta": delta, "item_id": f"msg_{resp_id}", "output_index": 0, "content_index": 0}
            yield f"event: response.output_text.delta\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
        completed = _response_object(resp_id, model, text)
        yield f"event: response.completed\ndata: {json.dumps({'type': 'response.completed', 'response': completed}, ensure_ascii=False)}\n\n"

    return StreamingResponse(_sse(), media_type="text/event-stream")


def _messages_text(messages: list) -> str:
    parts = []
    for message in messages:
        content = message.get("content")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") in ("text", "input_text"):
                    parts.append(str(block.get("text", "")))
    return "\n".join(parts)


_SKILL_ANSWERS = {
    "solve": "【解题演示】先通分：3/4 = 9/12，1/6 = 2/12，所以 3/4 + 1/6 = 11/12。",
    "check": "【批改演示】解答过程正确，通分与约分步骤完整，结果 11/12 无误。",
    "explain": "【讲解演示】异分母分数相加要先找最小公倍数通分，再把分子相加，分母保持不变。",
    "assess": "【学情评估演示】该生已掌握异分母分数加法，建议巩固最小公倍数的快速求解。",
}


def _chat_completion_body(body: dict) -> dict:
    messages = list(body.get("messages") or [])
    text = _messages_text(messages)
    has_tool_result = any(str(m.get("role", "")) == "tool" for m in messages)
    match = re.search(r"【子任务】技能=([a-z\-]+)", text)
    message: dict
    if match and not has_tool_result:
        skill = match.group(1)
        calls = [
            {
                "id": f"call_{uuid.uuid4().hex[:8]}",
                "type": "function",
                "function": {
                    "name": "note_state_patch",
                    "arguments": json.dumps(
                        {"key": "knowledge_point", "value": f"{skill}-异分母分数加法", "reason": "演示知识点沉淀"},
                        ensure_ascii=False,
                    ),
                },
            },
            {
                "id": f"call_{uuid.uuid4().hex[:8]}",
                "type": "function",
                "function": {
                    "name": "note_state_patch",
                    "arguments": json.dumps(
                        {"key": "session_id", "value": "hijack", "reason": "演示白名单拒绝"},
                        ensure_ascii=False,
                    ),
                },
            },
        ]
        message = {"role": "assistant", "content": None, "tool_calls": calls}
        finish = "tool_calls"
    else:
        skill = match.group(1) if match else ""
        answer = _SKILL_ANSWERS.get(skill) or f"【演示回复】{text[-160:]}"
        message = {"role": "assistant", "content": answer}
        finish = "stop"
    return {
        "id": _next_id("chatcmpl"),
        "object": "chat.completion",
        "created": int(time.time()),
        "model": str(body.get("model", "stub-model")),
        "choices": [{"index": 0, "message": message, "finish_reason": finish}],
        "usage": {"prompt_tokens": 32, "completion_tokens": 32, "total_tokens": 64},
    }


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    result = _chat_completion_body(body)
    if not body.get("stream"):
        return JSONResponse(result)

    choice = result["choices"][0]
    message = choice["message"]

    async def _sse():
        base = {"id": result["id"], "object": "chat.completion.chunk", "created": result["created"], "model": result["model"]}
        if message.get("tool_calls"):
            for index, call in enumerate(message["tool_calls"]):
                delta = {
                    "tool_calls": [
                        {
                            "index": index,
                            "id": call["id"],
                            "type": "function",
                            "function": {"name": call["function"]["name"], "arguments": call["function"]["arguments"]},
                        }
                    ]
                }
                yield f"data: {json.dumps({**base, 'choices': [{'index': 0, 'delta': delta, 'finish_reason': None}]}, ensure_ascii=False)}\n\n"
            finish = "tool_calls"
        else:
            content = str(message.get("content") or "")
            for index in range(0, len(content), 16):
                delta = {"content": content[index: index + 16]}
                yield f"data: {json.dumps({**base, 'choices': [{'index': 0, 'delta': delta, 'finish_reason': None}]}, ensure_ascii=False)}\n\n"
            finish = "stop"
        yield f"data: {json.dumps({**base, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': finish}]}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(_sse(), media_type="text/event-stream")


@app.get("/v1/models")
async def models():
    return {"object": "list", "data": [{"id": "stub-model", "object": "model"}]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8090)
    args = parser.parse_args()
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")