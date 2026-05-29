"""LLM 请求构建器。"""

from __future__ import annotations

from typing import Any

from ava.llm_model_executor.types import (
    InferenceRequest,
    InferenceTask,
    ModelRequestContext,
)
from configs import settings

_RESPONSES_ALLOWED_ROLES = {"system", "developer", "assistant", "user"}


def _normalize_role(role: str) -> str:
    normalized = str(role or "").strip()
    if normalized in _RESPONSES_ALLOWED_ROLES:
        return normalized
    if normalized in {"function", "tool"}:
        return "assistant"
    return "user"


def _normalize_content_part(part: dict[str, Any]) -> dict[str, Any] | None:
    part_type = str(part.get("type", "") or "").strip()
    if part_type in {"text", "input_text", "output_text"}:
        text = str(part.get("text", "") or "").strip()
        if not text:
            return None
        normalized_type = "output_text" if part_type == "output_text" else "input_text"
        return {"type": normalized_type, "text": text}

    if part_type in {"image_url", "input_image"}:
        if part_type == "image_url":
            image_url = part.get("image_url")
            if isinstance(image_url, dict):
                url = str(image_url.get("url", "") or "").strip()
                detail = str(image_url.get("detail", "auto") or "auto").strip()
            else:
                url = str(image_url or "").strip()
                detail = "auto"
        else:
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


class RequestPolicy:
    """根据任务和元信息解析请求参数。"""

    @staticmethod
    def resolve_model(context: ModelRequestContext) -> str:
        override = str((context.metadata or {}).get("model_override", "") or "").strip()
        if override:
            return override
        return str(context.model or "").strip()

    @staticmethod
    def resolve_timeout(context: ModelRequestContext) -> int:
        override = (context.metadata or {}).get("timeout")
        if override is not None:
            return int(override)
        if context.task == InferenceTask.ROUTE:
            return int(
                settings.runtime.router_timeout
                or settings.openai_config.intent_timeout
                or settings.openai_config.timeout
            )
        return int(settings.openai_config.timeout or 60)

    @staticmethod
    def resolve_temperature(context: ModelRequestContext) -> float:
        if context.task == InferenceTask.ROUTE:
            return 0.1
        return 0.7


class InferenceRequestBuilder:
    """把消息优先的模型请求上下文转换为 provider 可执行请求。"""

    def __init__(self, policy: RequestPolicy | None = None) -> None:
        self.policy = policy or RequestPolicy()

    def _build_responses_input(self, input_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized_items: list[dict[str, Any]] = []
        for message in input_items:
            item = dict(message or {})
            normalized_content = _normalize_message_content(item.get("content"))
            if normalized_content in ("", []):
                continue
            normalized_items.append(
                {
                    "type": "message",
                    "role": _normalize_role(str(item.get("role", "user") or "user")),
                    "content": normalized_content,
                }
            )
        return normalized_items

    def build(self, context: ModelRequestContext) -> InferenceRequest:
        payload: dict[str, Any] = {}
        instructions = str(context.instructions or "").strip()
        if instructions:
            payload["instructions"] = instructions

        messages = self._build_responses_input(list(context.messages or []))
        if messages:
            payload["input"] = messages

        temperature = self.policy.resolve_temperature(context)
        if temperature is not None:
            payload["temperature"] = temperature

        extra_body = dict((context.metadata or {}).get("extra_body") or {})
        if extra_body:
            payload.update(extra_body)

        return InferenceRequest(
            task=context.task,
            model=self.policy.resolve_model(context),
            payload=payload,
            stream=False,
            timeout=self.policy.resolve_timeout(context),
            metadata=dict(context.metadata or {}),
        )
