"""LLM provider 实现。"""

from __future__ import annotations

import threading
from typing import Any

from openai import OpenAI

from ava.llm_model_executor.types import (
    InferenceCompleted,
    InferenceError,
    InferenceRequest,
    InferenceResult,
    OutputTextDelta,
)
from ava.core.runtime.errors import DashScopeError
from configs import settings


def _extract_text_content(content: Any) -> str:
    if isinstance(content, list):
        parts = [
            part.get("text", "")
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        ]
        content = "".join(parts)
    return (content or "").strip()


def _extract_response_metadata(response: Any) -> dict[str, Any]:
    response_id = getattr(response, "id", None)
    conversation = getattr(response, "conversation", None)
    conversation_id = None
    if isinstance(conversation, str):
        conversation_id = conversation
    elif conversation is not None:
        conversation_id = getattr(conversation, "id", None) or getattr(conversation, "conversation_id", None)

    if conversation_id is None and isinstance(response, dict):
        conversation_value = response.get("conversation")
        if isinstance(conversation_value, str):
            conversation_id = conversation_value
        elif isinstance(conversation_value, dict):
            conversation_id = conversation_value.get("id") or conversation_value.get("conversation_id")
        response_id = response_id or response.get("id")

    return {
        "response_id": response_id,
        "conversation_id": conversation_id,
    }


class OpenAIResponsesProvider:
    """基于 OpenAI SDK Responses API 的 provider。

    provider 只负责执行请求：
    - 初始化 SDK client
    - 调用 `client.responses.create(...)`
    - 解析同步 / 流式返回

    payload 的组装全部由外层完成后放入 `InferenceRequest.payload`。
    """

    def __init__(
        self,
        *,
        api_base: str,
        api_key: str,
    ) -> None:
        self.api_base = api_base
        self.api_key = api_key
        self.client = OpenAI(api_key=api_key, base_url=api_base)

    @classmethod
    def from_settings(cls) -> "OpenAIResponsesProvider":
        return cls(
            api_base=settings.openai_config.api_base,
            api_key=settings.openai_config.api_key,
        )

    def chat(self, request: InferenceRequest) -> InferenceResult:
        """执行同步请求。"""
        try:
            response = self.client.responses.create(
                model=request.model,
                timeout=request.timeout,
                **dict(request.payload or {}),
            )
        except Exception as exc:
            raise DashScopeError(f"LLM request failed: {exc}") from exc

        response_metadata = _extract_response_metadata(response)
        return InferenceResult(
            text=_extract_text_content(getattr(response, "output_text", "")),
            raw=response,
            usage=getattr(response, "usage", None),
            finish_reason=(
                getattr(getattr(response, "incomplete_details", None), "reason", None)
                or getattr(response, "status", None)
            ),
            metadata={
                "model": request.model,
                **response_metadata,
            },
        )

    def stream(
        self,
        request: InferenceRequest,
        *,
        stop_event: threading.Event | None = None,
    ):
        """执行流式请求。"""
        text_parts: list[str] = []
        completed_metadata = {
            "model": request.model,
            "response_id": None,
            "conversation_id": dict(request.payload or {}).get("conversation"),
        }

        try:
            stream = self.client.responses.create(
                model=request.model,
                stream=True,
                timeout=request.timeout,
                **dict(request.payload or {}),
            )
            for event in stream:
                if stop_event is not None and stop_event.is_set():
                    break
                event_type = str(getattr(event, "type", "") or "")
                if event_type == "response.output_text.delta":
                    text = str(getattr(event, "delta", "") or "")
                    if text:
                        text_parts.append(text)
                        yield OutputTextDelta(text=text)
                elif event_type == "response.completed":
                    completed_metadata.update(
                        _extract_response_metadata(getattr(event, "response", None) or event)
                    )
        except Exception as exc:
            yield InferenceError(error=str(exc))
            return

        yield InferenceCompleted(
            text="".join(text_parts),
            finish_reason=None,
            metadata=completed_metadata,
        )
