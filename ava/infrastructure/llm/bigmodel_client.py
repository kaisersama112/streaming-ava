"""BigModel multimodal client built on the OpenAI-compatible SDK."""

from __future__ import annotations

from typing import Any


def multimodal_chat(
    api_base: str,
    api_key: str,
    model: str,
    messages: list[dict[str, Any]],
    timeout: int = 15,
    temperature: float | None = 0.0,
    extra_body: dict[str, Any] | None = None,
) -> str:
    from . import client

    return client.chat(
        api_base=api_base,
        api_key=api_key,
        model=model,
        messages=messages,
        timeout=timeout,
        temperature=temperature,
        extra_body=extra_body,
    )
