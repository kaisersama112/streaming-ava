"""Model and run-config helpers for OpenAI Agents SDK execution."""

from __future__ import annotations

from dataclasses import dataclass

from openai import AsyncOpenAI
from agents import ModelSettings, OpenAIChatCompletionsModel, RunConfig

from ava.domain.context import ContextSnapshot
from config import settings


@dataclass(frozen=True)
class AgentsModelConfig:
    api_base: str
    api_key: str
    model: str
    multimodal_model: str
    timeout: int


def _resolve_model_config(
    *,
    api_base: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
    multimodal_model: str | None = None,
    timeout: int | None = None,
) -> AgentsModelConfig:
    return AgentsModelConfig(
        api_base=str(api_base or settings.openai_config.api_base or "").strip(),
        api_key=str(api_key or settings.openai_config.api_key or "").strip(),
        model=str(model or settings.openai_config.model or "").strip(),
        multimodal_model=str(multimodal_model or settings.openai_config.multimodal_model or "").strip(),
        timeout=int(timeout or getattr(settings.runtime, "agents_sdk_timeout", settings.openai_config.timeout) or settings.openai_config.timeout),
    )


def _select_model_name(snapshot: ContextSnapshot, model_config: AgentsModelConfig) -> str:
    has_multimodal_input = bool(snapshot.artifacts or snapshot.reference_artifacts)
    if has_multimodal_input:
        return (
            str(getattr(settings.runtime, "agents_sdk_multimodal_model", "") or "").strip()
            or model_config.multimodal_model
            or model_config.model
        )
    return (
        str(getattr(settings.runtime, "agents_sdk_model", "") or "").strip()
        or model_config.model
        or model_config.multimodal_model
    )


def build_agents_sdk_model(
    snapshot: ContextSnapshot,
    *,
    api_base: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
    multimodal_model: str | None = None,
    timeout: int | None = None,
) -> OpenAIChatCompletionsModel:
    model_config = _resolve_model_config(
        api_base=api_base,
        api_key=api_key,
        model=model,
        multimodal_model=multimodal_model,
        timeout=timeout,
    )
    client = AsyncOpenAI(
        api_key=model_config.api_key,
        base_url=model_config.api_base,
        timeout=model_config.timeout,
    )
    return OpenAIChatCompletionsModel(
        model=_select_model_name(snapshot, model_config),
        openai_client=client,
    )


def build_agents_sdk_model_settings() -> ModelSettings:
    return ModelSettings(
        temperature=0.35,
        parallel_tool_calls=False,
    )


def build_agents_sdk_run_config(*, workflow_name: str, trace_id: str | None = None) -> RunConfig:
    tracing_enabled = bool(getattr(settings.runtime, "agents_sdk_tracing_enabled", False))
    return RunConfig(
        workflow_name=workflow_name,
        trace_id=trace_id,
        tracing_disabled=not tracing_enabled,
    )
