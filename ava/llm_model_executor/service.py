"""模型执行器主实现。"""

from __future__ import annotations

import threading
from typing import Any

import httpx
from openai import OpenAI

from configs import settings

from .types import (
    InferenceCompleted,
    InferenceError,
    InferenceRequest,
    InferenceResult,
    InferenceTask,
    ModelRequestContext,
    OutputTextDelta,
)

_ALLOWED_ROLES = {"system", "developer", "user", "assistant"}


def _normalize_role(role: str) -> str:
    value = str(role or "").strip()
    if value in _ALLOWED_ROLES:
        return value
    if value in {"tool", "function"}:
        return "assistant"
    return "user"


def _normalize_content_part(part: dict[str, Any]) -> dict[str, Any] | None:
    part_type = str(part.get("type", "") or "").strip()
    if part_type in {"text", "input_text", "output_text"}:
        text = str(part.get("text", "") or "").strip()
        if not text:
            return None
        return {
            "type": "output_text" if part_type == "output_text" else "input_text",
            "text": text,
        }

    if part_type in {"image_url", "input_image"}:
        if part_type == "image_url":
            payload = part.get("image_url")
            if isinstance(payload, dict):
                image_url = str(payload.get("url", "") or "").strip()
                detail = str(payload.get("detail", "auto") or "auto").strip()
            else:
                image_url = str(payload or "").strip()
                detail = "auto"
        else:
            image_url = str(part.get("image_url", "") or "").strip()
            detail = str(part.get("detail", "auto") or "auto").strip()
        if not image_url:
            return None
        return {"type": "input_image", "image_url": image_url, "detail": detail}

    if part_type == "input_audio":
        payload = dict(part.get("input_audio") or {})
        audio_data = str(payload.get("data", "") or "").strip()
        audio_format = str(payload.get("format", "") or "").strip()
        if not audio_data or not audio_format:
            return None
        return {
            "type": "input_audio",
            "input_audio": {"data": audio_data, "format": audio_format},
        }

    if part_type == "video":
        videos = part.get("video") or []
        if not isinstance(videos, list):
            return None
        first = next((str(item).strip() for item in videos if str(item).strip()), "")
        if not first:
            return None
        return {"type": "input_file", "file_url": first, "filename": "video"}

    if part_type == "input_file":
        normalized = {"type": "input_file"}
        for key in ("file_id", "file_data", "file_url", "filename"):
            value = part.get(key)
            if value not in (None, ""):
                normalized[key] = value
        return normalized if len(normalized) > 1 else None

    return None


def _normalize_content(content: Any) -> str | list[dict[str, Any]]:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, dict):
        normalized = _normalize_content_part(content)
        return [normalized] if normalized is not None else []
    if isinstance(content, list):
        normalized_parts: list[dict[str, Any]] = []
        for part in content:
            if isinstance(part, dict):
                normalized = _normalize_content_part(part)
                if normalized is not None:
                    normalized_parts.append(normalized)
        return normalized_parts
    return str(content or "").strip()


class RequestPolicy:
    """请求参数策略。"""

    @staticmethod
    def resolve_model(context: ModelRequestContext) -> str:
        override = str((context.metadata or {}).get("model_override", "") or "").strip()
        return override or str(context.model or "").strip()

    @staticmethod
    def resolve_timeout(context: ModelRequestContext) -> float:
        override = (context.metadata or {}).get("timeout")
        if override is not None:
            return float(override)
        if context.task == InferenceTask.ROUTE:
            return int(getattr(settings.runtime, "router_timeout", 30) or 30)
        return int(getattr(settings.openai_config, "timeout", 60) or 60)

    @staticmethod
    def resolve_temperature(context: ModelRequestContext) -> float:
        if context.task == InferenceTask.ROUTE:
            return 0.1
        return 0.7


class OpenAIResponsesProvider:
    """对 OpenAI Responses API 的最小封装。"""

    def __init__(self, *, api_base: str, api_key: str) -> None:
        self.api_base = str(api_base or "").strip()
        self.api_key = str(api_key or "").strip()

    @classmethod
    def from_settings(cls) -> "OpenAIResponsesProvider":
        return cls(
            api_base=str(getattr(settings.openai_config, "api_base", "") or "").strip(),
            api_key=str(getattr(settings.openai_config, "api_key", "") or "").strip(),
        )

    def _client(self, *, timeout: float | None = None) -> OpenAI:
        kwargs: dict[str, Any] = {"api_key": self.api_key}
        if self.api_base:
            kwargs["base_url"] = self.api_base
        if timeout is not None:
            kwargs["timeout"] = timeout
        # Windows 注册表代理可能含非法 IPv6 项，trust_env 会让 httpx 构造期崩溃
        kwargs["http_client"] = httpx.Client(trust_env=False, timeout=timeout if timeout is not None else 60.0)
        return OpenAI(**kwargs)

    @staticmethod
    def _extract_text(response: Any) -> str:
        output_text = getattr(response, "output_text", None)
        if isinstance(output_text, str) and output_text.strip():
            return output_text.strip()

        parts: list[str] = []
        for output_item in list(getattr(response, "output", []) or []):
            for content in list(getattr(output_item, "content", []) or []):
                text = getattr(content, "text", None)
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
        return "\n".join(parts).strip()

    def chat(self, request: InferenceRequest) -> InferenceResult:
        client = self._client(timeout=request.timeout)
        response = client.responses.create(model=request.model, **dict(request.payload or {}))
        return InferenceResult(
            text=self._extract_text(response),
            raw=response,
            usage=getattr(response, "usage", None),
            finish_reason=getattr(response, "status", None),
            metadata={"response_id": getattr(response, "id", "")},
        )

    def stream(self, request: InferenceRequest, *, stop_event=None):
        client = self._client(timeout=request.timeout)
        final_parts: list[str] = []
        response_meta: dict[str, Any] = {}

        def _capture(response_obj: Any) -> None:
            response_id = str(getattr(response_obj, "id", "") or "")
            if response_id:
                response_meta["response_id"] = response_id
            conversation = getattr(response_obj, "conversation", None)
            conversation_id = str(getattr(conversation, "id", "") or "") if conversation is not None else ""
            if conversation_id:
                response_meta["conversation_id"] = conversation_id

        try:
            stream = client.responses.create(
                model=request.model,
                stream=True,
                **dict(request.payload or {}),
            )
            for event in stream:
                if stop_event is not None and stop_event.is_set():
                    break
                event_type = str(getattr(event, "type", "") or "").strip()
                if event_type == "response.output_text.delta":
                    delta = str(getattr(event, "delta", "") or "")
                    if delta:
                        final_parts.append(delta)
                        yield OutputTextDelta(delta)
                    continue
                if event_type in {"response.created", "response.completed", "response.incomplete"}:
                    _capture(getattr(event, "response", None))
                if event_type == "response.completed":
                    yield InferenceCompleted(
                        text="".join(final_parts),
                        finish_reason="completed",
                        metadata=dict(response_meta),
                    )
                    return
            yield InferenceCompleted(
                text="".join(final_parts),
                finish_reason="completed",
                metadata=dict(response_meta),
            )
        except Exception as exc:
            yield InferenceError(error=str(exc))


class LLMService:
    """只做模型执行，不做上下文构造。"""

    def __init__(
            self,
            *,
            provider: OpenAIResponsesProvider | None = None,
            policy: RequestPolicy | None = None,
    ) -> None:
        self.provider = provider or OpenAIResponsesProvider.from_settings()
        self.policy = policy or RequestPolicy()

    def _build_request_input(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized_items: list[dict[str, Any]] = []
        for item in items:
            role = _normalize_role(str(item.get("role", "user") or "user"))
            content = _normalize_content(item.get("content"))
            if content in ("", []):
                continue
            normalized_items.append(
                {
                    "type": "message",
                    "role": role,
                    "content": content,
                }
            )
        return normalized_items

    def build_request(self, context: ModelRequestContext, *, stream: bool = False) -> InferenceRequest:
        """把纯请求上下文转成 provider 请求。"""

        payload: dict[str, Any] = {}
        instructions = str(context.instructions or "").strip()
        if instructions:
            payload["instructions"] = instructions

        metadata = dict(context.metadata or {})
        previous_response_id = str(metadata.get("previous_response_id") or "").strip()
        conversation_id = str(metadata.get("conversation_id") or "").strip()
        raw_items = list(context.input or [])
        if previous_response_id or conversation_id:
            # 模型侧连续对话：历史由 Responses API 维护，本地只喂当前轮用户消息
            raw_items = raw_items[-1:] if raw_items else []
        input_items = self._build_request_input(raw_items)
        if input_items:
            payload["input"] = input_items
        if previous_response_id:
            payload["previous_response_id"] = previous_response_id
        if conversation_id:
            payload["conversation"] = conversation_id

        payload["temperature"] = self.policy.resolve_temperature(context)
        extra_body = dict(metadata.get("extra_body") or {})
        if extra_body:
            payload.update(extra_body)

        return InferenceRequest(
            task=context.task,
            model=self.policy.resolve_model(context),
            payload=payload,
            stream=stream,
            timeout=self.policy.resolve_timeout(context),
            metadata=metadata,
        )

    def _provider_for(self, context: ModelRequestContext) -> OpenAIResponsesProvider:
        """按请求 metadata 选择端点（小模型本地端点 / 云侧兜底真实生效）。"""
        metadata = dict(context.metadata or {})
        api_base = str(metadata.get("api_base") or "").strip()
        api_key = str(metadata.get("api_key") or "").strip()
        if api_base and (api_base != self.provider.api_base or api_key != self.provider.api_key):
            return OpenAIResponsesProvider(api_base=api_base, api_key=api_key or self.provider.api_key)
        return self.provider

    def route(self, context: ModelRequestContext) -> InferenceResult:
        return self.execute(context)

    def generate(self, context: ModelRequestContext) -> InferenceResult:
        return self.execute(context)

    def execute(self, context: ModelRequestContext) -> InferenceResult:
        request = self.build_request(context)
        return self._provider_for(context).chat(request)

    def stream_generate(
            self,
            context: ModelRequestContext,
            *,
            stop_event: threading.Event | None = None,
    ):
        request = self.build_request(context, stream=True)
        yield from self._provider_for(context).stream(request, stop_event=stop_event)
