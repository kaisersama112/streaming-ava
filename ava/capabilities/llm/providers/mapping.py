from typing import Any

from ava.capabilities.llm.types import InferenceRequest

_RESPONSES_ALLOWED_ROLES = {"system", "developer", "assistant", "user"}


def _normalize_role(role: str) -> str:
    normalized = str(role or "").strip()
    if normalized in _RESPONSES_ALLOWED_ROLES:
        return normalized
    if normalized == "function":
        return "assistant"
    if normalized == "tool":
        return "assistant"
    return "user"


def _normalize_content_part(part: dict[str, Any]) -> dict[str, Any] | None:
    part_type = str(part.get("type", "") or "").strip()
    if part_type == "text":
        text = str(part.get("text", "") or "").strip()
        if not text:
            return None
        return {"type": "input_text", "text": text}
    if part_type == "input_text":
        text = str(part.get("text", "") or "").strip()
        if not text:
            return None
        return {"type": "input_text", "text": text}
    if part_type == "image_url":
        image_url = part.get("image_url")
        if isinstance(image_url, dict):
            url = str(image_url.get("url", "") or "").strip()
            detail = str(image_url.get("detail", "auto") or "auto").strip()
        else:
            url = str(image_url or "").strip()
            detail = "auto"
        if not url:
            return None
        return {
            "type": "input_image",
            "image_url": url,
            "detail": detail,
        }
    if part_type == "input_image":
        url = str(part.get("image_url", "") or "").strip()
        detail = str(part.get("detail", "auto") or "auto").strip()
        if not url:
            return None
        return {
            "type": "input_image",
            "image_url": url,
            "detail": detail,
        }
    if part_type == "input_audio":
        payload = dict(part.get("input_audio") or {})
        audio_data = str(payload.get("data", "") or "").strip()
        audio_format = str(payload.get("format", "") or "").strip()
        if not audio_data or not audio_format:
            return None
        return {
            "type": "input_audio",
            "input_audio": {
                "data": audio_data,
                "format": audio_format,
            },
        }
    if part_type == "input_file":
        item = {"type": "input_file"}
        for key in ("file_id", "file_data", "file_url", "filename"):
            value = part.get(key)
            if value not in (None, ""):
                item[key] = value
        return item if len(item) > 1 else None
    if part_type == "video":
        video_items = part.get("video") or []
        if not isinstance(video_items, list):
            return None
        first_item = next((str(item).strip() for item in video_items if str(item).strip()), "")
        if not first_item:
            return None
        return {
            "type": "input_file",
            "file_url": first_item,
            "filename": "video",
        }
    return None


def _normalize_message_content(content: Any) -> str | list[dict[str, Any]]:
    if isinstance(content, str):
        text = content.strip()
        return text if text else ""
    if isinstance(content, list):
        normalized_parts: list[dict[str, Any]] = []
        for part in content:
            if isinstance(part, dict):
                normalized = _normalize_content_part(part)
                if normalized is not None:
                    normalized_parts.append(normalized)
        return normalized_parts
    if isinstance(content, dict):
        normalized = _normalize_content_part(content)
        if normalized is None:
            return ""
        return [normalized]
    text = str(content or "").strip()
    return text if text else ""


def build_responses_input(request: InferenceRequest) -> list[dict[str, Any]]:
    input_items: list[dict[str, Any]] = []
    for message in request.input_items:
        item = dict(message or {})
        normalized_content = _normalize_message_content(item.get("content"))
        if normalized_content in ("", []):
            continue
        input_items.append(
            {
                "type": "message",
                "role": _normalize_role(str(item.get("role", "user") or "user")),
                "content": normalized_content,
            }
        )
    return input_items


def build_request_kwargs(request: InferenceRequest) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    instructions = str(request.instructions or "").strip()
    if instructions:
        payload["instructions"] = instructions
    if request.input_items:
        payload["input"] = build_responses_input(request)
    if request.conversation not in (None, ""):
        payload["conversation"] = request.conversation
    if request.previous_response_id:
        payload["previous_response_id"] = request.previous_response_id
    if request.temperature is not None:
        payload["temperature"] = request.temperature
    if request.max_output_tokens is not None:
        payload["max_output_tokens"] = int(request.max_output_tokens)
    if request.response_format:
        payload["text"] = {"format": dict(request.response_format)}
    if request.tools:
        payload["tools"] = list(request.tools)
    if request.extra_body:
        payload.update(dict(request.extra_body))
    return payload
