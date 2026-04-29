"""OpenAI-compatible client with SDK-first and HTTP fallback paths."""

from __future__ import annotations

import json
import threading
from typing import Any, Iterable
from urllib import error as urllib_error
from urllib import request as urllib_request

from ava.shared.errors import DashScopeError


def _build_client(api_base: str, api_key: str):
    try:
        from openai import OpenAI  # type: ignore
    except Exception:
        return None
    return OpenAI(api_key=api_key, base_url=api_base)


def _build_request_kwargs(
        temperature: float | None = None,
        extra_body: dict[str, Any] | None = None,
        modalities: Iterable[str] | None = None,
        stream_options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if temperature is not None:
        payload["temperature"] = temperature
    if modalities is not None:
        payload["modalities"] = list(modalities)
    if stream_options is not None:
        payload["stream_options"] = stream_options
    if extra_body:
        payload.update(extra_body)
    return payload


def _extract_text_content(content: Any) -> str:
    if isinstance(content, list):
        text_parts = [
            part.get("text", "")
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        ]
        content = "".join(text_parts)
    return (content or "").strip()


def _http_request(
        api_base: str,
        api_key: str,
        payload: dict[str, Any],
        *,
        timeout: int,
):
    endpoint = api_base.rstrip("/") + "/chat/completions"
    request = urllib_request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    return urllib_request.urlopen(request, timeout=timeout)


def _chat_via_http(
        api_base: str,
        api_key: str,
        model: str,
        messages: list[dict[str, Any]],
        timeout: int = 60,
        temperature: float | None = None,
        extra_body: dict[str, Any] | None = None,
        modalities: Iterable[str] | None = None,
) -> str:
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
    }
    payload.update(
        _build_request_kwargs(
            temperature=temperature,
            extra_body=extra_body,
            modalities=modalities,
        )
    )
    try:
        with _http_request(api_base, api_key, payload, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib_error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise DashScopeError(f"LLM request failed: HTTP {exc.code} {detail}") from exc
    except Exception as exc:
        raise DashScopeError(f"LLM request failed: {exc}") from exc

    choices = body.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    return _extract_text_content(message.get("content"))


def _chat_stream_via_http(
        api_base: str,
        api_key: str,
        model: str,
        messages: list[dict[str, Any]],
        timeout: int = 60,
        temperature: float | None = None,
        extra_body: dict[str, Any] | None = None,
        modalities: Iterable[str] | None = None,
        stream_options: dict[str, Any] | None = None,
        stop_event: threading.Event | None = None,
):
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": True,
    }
    payload.update(
        _build_request_kwargs(
            temperature=temperature,
            extra_body=extra_body,
            modalities=modalities,
            stream_options=stream_options,
        )
    )
    try:
        with _http_request(api_base, api_key, payload, timeout=timeout) as resp:
            for raw_line in resp:
                if stop_event is not None and stop_event.is_set():
                    break
                line = raw_line.decode("utf-8", errors="ignore").strip()
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if not data or data == "[DONE]":
                    continue
                chunk = json.loads(data)
                choices = chunk.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                content = delta.get("content")
                text = _extract_text_content(content)
                if text:
                    yield text
    except urllib_error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise DashScopeError(f"LLM stream request failed: HTTP {exc.code} {detail}") from exc
    except Exception as exc:
        raise DashScopeError(f"LLM stream request failed: {exc}") from exc


def chat(
        api_base: str,
        api_key: str,
        model: str,
        messages: list[dict[str, Any]],
        timeout: int = 60,
        temperature: float | None = None,
        extra_body: dict[str, Any] | None = None,
        modalities: Iterable[str] | None = None,
) -> str:
    client = _build_client(api_base, api_key)
    if client is None:
        return _chat_via_http(
            api_base=api_base,
            api_key=api_key,
            model=model,
            messages=messages,
            timeout=timeout,
            temperature=temperature,
            extra_body=extra_body,
            modalities=modalities,
        )
    try:
        completion = client.chat.completions.create(
            model=model,
            messages=messages,
            timeout=timeout,
            **_build_request_kwargs(
                temperature=temperature,
                extra_body=extra_body,
                modalities=modalities,
            ),
        )
        return _extract_text_content(completion.choices[0].message.content)
    except Exception as exc:
        raise DashScopeError(f"LLM request failed: {exc}") from exc


def chat_stream(
        api_base: str,
        api_key: str,
        model: str,
        messages: list[dict[str, Any]],
        timeout: int = 60,
        temperature: float | None = None,
        extra_body: dict[str, Any] | None = None,
        modalities: Iterable[str] | None = None,
        stream_options: dict[str, Any] | None = None,
        stop_event: threading.Event | None = None,
):
    client = _build_client(api_base, api_key)
    if client is None:
        yield from _chat_stream_via_http(
            api_base=api_base,
            api_key=api_key,
            model=model,
            messages=messages,
            timeout=timeout,
            temperature=temperature,
            extra_body=extra_body,
            modalities=modalities,
            stream_options=stream_options,
            stop_event=stop_event,
        )
        return
    try:
        stream = client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True,
            timeout=timeout,
            **_build_request_kwargs(
                temperature=temperature,
                extra_body=extra_body,
                modalities=modalities,
                stream_options=stream_options,
            ),
        )
        for chunk in stream:
            if stop_event is not None and stop_event.is_set():
                break
            if not getattr(chunk, "choices", None):
                continue
            delta = chunk.choices[0].delta
            content = getattr(delta, "content", None)
            text = _extract_text_content(content)
            if text:
                yield text
    except Exception as exc:
        raise DashScopeError(f"LLM stream request failed: {exc}") from exc
