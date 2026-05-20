import json
import threading
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

from ava.core.runtime.errors import DashScopeError
from configs import settings

from ava.capabilities.llm.providers.mapping import build_request_kwargs
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


def _supports_responses_api(client: Any) -> bool:
    responses = getattr(client, "responses", None)
    return bool(responses is not None and hasattr(responses, "create"))


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


def _maybe_create_conversation_id(client: Any) -> str | None:
    conversations = getattr(client, "conversations", None)
    if conversations is None or not hasattr(conversations, "create"):
        return None
    try:
        conversation = conversations.create()
    except Exception:
        return None
    return getattr(conversation, "id", None)


def _http_request(
    api_base: str,
    api_key: str,
    endpoint: str,
    payload: dict[str, Any],
    *,
    timeout: float | None,
):
    request = urllib_request.Request(
        api_base.rstrip("/") + endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    return urllib_request.urlopen(request, timeout=timeout or 60)


def _extract_output_text_from_response_payload(payload: dict[str, Any]) -> str:
    output_text = payload.get("output_text")
    if isinstance(output_text, str):
        return output_text.strip()

    parts: list[str] = []
    for item in payload.get("output") or []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content") or []:
            if not isinstance(content, dict):
                continue
            text = str(content.get("text", "") or "").strip()
            if text:
                parts.append(text)
    return "".join(parts).strip()


def _create_conversation_via_http(
    api_base: str,
    api_key: str,
    *,
    timeout: float | None,
) -> str | None:
    try:
        with _http_request(api_base, api_key, "/conversations", {}, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None
    if isinstance(payload, dict):
        return str(payload.get("id", "") or "").strip() or None
    return None


def _prepare_payload(
    *,
    client: Any,
    api_base: str,
    api_key: str,
    request: InferenceRequest,
) -> dict[str, Any]:
    payload = build_request_kwargs(request)
    if (
        request.task.value == "generate"
        and "conversation" not in payload
        and bool((request.metadata or {}).get("use_conversation_state", False))
    ):
        conversation_id = None
        if client is not None:
            conversation_id = _maybe_create_conversation_id(client)
        if conversation_id is None:
            conversation_id = _create_conversation_via_http(
                api_base,
                api_key,
                timeout=request.timeout,
            )
        if conversation_id:
            payload["conversation"] = conversation_id
    return payload


def _chat_via_http(
    *,
    api_base: str,
    api_key: str,
    request: InferenceRequest,
    payload: dict[str, Any],
) -> InferenceResult:
    body = {"model": request.model, **payload}
    try:
        with _http_request(api_base, api_key, "/responses", body, timeout=request.timeout) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except urllib_error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise DashScopeError(f"LLM request failed: HTTP {exc.code} {detail}") from exc
    except Exception as exc:
        raise DashScopeError(f"LLM request failed: {exc}") from exc

    response_metadata = _extract_response_metadata(response_payload)
    return InferenceResult(
        text=_extract_output_text_from_response_payload(response_payload),
        raw=response_payload,
        usage=response_payload.get("usage"),
        finish_reason=(
            ((response_payload.get("incomplete_details") or {}).get("reason"))
            or response_payload.get("status")
        ),
        metadata={
            "model": request.model,
            **response_metadata,
        },
    )


def _stream_via_http(
    *,
    api_base: str,
    api_key: str,
    request: InferenceRequest,
    payload: dict[str, Any],
    stop_event: threading.Event | None,
):
    body = {"model": request.model, "stream": True, **payload}
    text_parts: list[str] = []
    completed_metadata = {
        "model": request.model,
        "response_id": None,
        "conversation_id": payload.get("conversation"),
    }
    try:
        with _http_request(api_base, api_key, "/responses", body, timeout=request.timeout) as response:
            for raw_line in response:
                if stop_event is not None and stop_event.is_set():
                    break
                line = raw_line.decode("utf-8", errors="ignore").strip()
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if not data or data == "[DONE]":
                    continue
                event = json.loads(data)
                event_type = str(event.get("type", "") or "")
                if event_type == "response.output_text.delta":
                    text = str(event.get("delta", "") or "")
                    if text:
                        text_parts.append(text)
                        yield OutputTextDelta(text=text)
                elif event_type == "response.completed":
                    completed_metadata.update(
                        _extract_response_metadata(event.get("response") or event)
                    )
    except urllib_error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        yield InferenceError(error=f"HTTP {exc.code} {detail}")
        return
    except Exception as exc:
        yield InferenceError(error=str(exc))
        return

    yield InferenceCompleted(
        text="".join(text_parts),
        finish_reason=None,
        metadata=completed_metadata,
    )


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
        payload = _prepare_payload(
            client=client,
            api_base=self.api_base,
            api_key=self.api_key,
            request=request,
        )
        if client is None or not _supports_responses_api(client):
            return _chat_via_http(
                api_base=self.api_base,
                api_key=self.api_key,
                request=request,
                payload=payload,
            )
        try:
            response = client.responses.create(
                model=request.model,
                timeout=request.timeout,
                **payload,
            )
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
        except Exception as exc:
            raise DashScopeError(f"LLM request failed: {exc}") from exc

    def stream(
        self,
        request: InferenceRequest,
        *,
        stop_event: threading.Event | None = None,
    ):
        client = _build_client(self.api_base, self.api_key)
        payload = _prepare_payload(
            client=client,
            api_base=self.api_base,
            api_key=self.api_key,
            request=request,
        )
        if client is None or not _supports_responses_api(client):
            yield from _stream_via_http(
                api_base=self.api_base,
                api_key=self.api_key,
                request=request,
                payload=payload,
                stop_event=stop_event,
            )
            return
        text_parts: list[str] = []
        try:
            stream = client.responses.create(
                model=request.model,
                stream=True,
                timeout=request.timeout,
                **payload,
            )
            completed_metadata = {
                "model": request.model,
                "response_id": None,
                "conversation_id": payload.get("conversation"),
            }
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
            yield InferenceCompleted(
                text="".join(text_parts),
                finish_reason=None,
                metadata=completed_metadata,
            )
        except Exception as exc:
            yield InferenceError(error=str(exc))
