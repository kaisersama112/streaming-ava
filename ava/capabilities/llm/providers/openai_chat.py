import threading
from typing import Any

from ava.core.runtime.errors import DashScopeError
from configs import settings

from ava.capabilities.llm.providers.mapping import build_messages, build_request_kwargs
from ava.capabilities.llm.streaming.events import (
    InferenceCompleted,
    InferenceError,
    OutputTextDelta,
)
from ava.capabilities.llm.types import InferenceRequest, InferenceResult


def _build_client(api_base: str, api_key: str):
    try:
        from openai import OpenAI  # type: ignore
    except Exception:
        return None
    return OpenAI(api_key=api_key, base_url=api_base)


def _extract_text_content(content: Any) -> str:
    if isinstance(content, list):
        parts = [
            part.get("text", "")
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        ]
        content = "".join(parts)
    return (content or "").strip()


class OpenAIChatProvider:
    def __init__(self, *, api_base: str, api_key: str) -> None:
        self.api_base = api_base
        self.api_key = api_key

    @classmethod
    def from_settings(cls) -> "OpenAIChatProvider":
        return cls(
            api_base=settings.openai_config.api_base,
            api_key=settings.openai_config.api_key,
        )

    def chat(self, request: InferenceRequest) -> InferenceResult:
        client = _build_client(self.api_base, self.api_key)
        if client is None:
            raise DashScopeError("OpenAI client is not available.")
        try:
            completion = client.chat.completions.create(
                model=request.model,
                messages=build_messages(request),
                timeout=request.timeout,
                **build_request_kwargs(request),
            )
            message = completion.choices[0].message
            return InferenceResult(
                text=_extract_text_content(message.content),
                raw=completion,
                usage=getattr(completion, "usage", None),
                finish_reason=getattr(completion.choices[0], "finish_reason", None),
                metadata={"model": request.model},
            )
        except Exception as exc:
            raise DashScopeError(f"LLM request failed: {exc}") from exc

    def stream(
        self,
        request: InferenceRequest,
        *,
        stop_event: threading.Event | None = None,
    ):
        client = _build_client(self.api_base, self.api_key)
        if client is None:
            raise DashScopeError("OpenAI client is not available.")
        text_parts: list[str] = []
        try:
            stream = client.chat.completions.create(
                model=request.model,
                messages=build_messages(request),
                stream=True,
                timeout=request.timeout,
                **build_request_kwargs(request),
            )
            for chunk in stream:
                if stop_event is not None and stop_event.is_set():
                    break
                if not getattr(chunk, "choices", None):
                    continue
                choice = chunk.choices[0]
                delta = getattr(choice, "delta", None)
                content = getattr(delta, "content", None)
                text = _extract_text_content(content)
                if text:
                    text_parts.append(text)
                    yield OutputTextDelta(text=text)
            yield InferenceCompleted(
                text="".join(text_parts),
                finish_reason=None,
            )
        except Exception as exc:
            yield InferenceError(error=str(exc))

