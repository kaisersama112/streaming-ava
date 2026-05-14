from typing import Any

from ava.capabilities.llm.types import InferenceRequest

_CHAT_COMPLETION_ALLOWED_ROLES = {"system", "assistant", "user", "tool", "function"}


def normalize_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for message in messages:
        item = dict(message or {})
        role = str(item.get("role", "") or "").strip()
        if role not in _CHAT_COMPLETION_ALLOWED_ROLES:
            item["role"] = "user"
        normalized.append(item)
    return normalized


def build_messages(request: InferenceRequest) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    instructions = str(request.instructions or "").strip()
    if instructions:
        messages.append({"role": "system", "content": instructions})
    if request.history:
        messages.extend(request.history)
    messages.append({"role": "user", "content": request.input})
    return normalize_messages(messages)


def build_request_kwargs(request: InferenceRequest) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if request.temperature is not None:
        payload["temperature"] = request.temperature
    if request.modalities:
        payload["modalities"] = list(request.modalities)
    if request.max_tokens is not None:
        payload["max_tokens"] = int(request.max_tokens)
    if request.response_format:
        payload["response_format"] = dict(request.response_format)
    if request.tools:
        payload["tools"] = list(request.tools)
    if request.extra_body:
        payload.update(dict(request.extra_body))
    return payload

