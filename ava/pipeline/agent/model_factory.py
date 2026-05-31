"""Agents SDK 模型与运行配置辅助。"""

from __future__ import annotations

from dataclasses import dataclass

from openai import AsyncOpenAI
from agents import ModelSettings, OpenAIChatCompletionsModel, RunConfig

from configs import settings


@dataclass(frozen=True)
class AgentsModelConfig:
    api_base: str
    api_key: str
    model: str
    timeout: int


def _resolve_model_config(
    *,
    api_base: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
    timeout: int | None = None,
) -> AgentsModelConfig:
    return AgentsModelConfig(
        api_base=str(api_base or settings.openai_config.api_base or "").strip(),
        api_key=str(api_key or settings.openai_config.api_key or "").strip(),
        model=str(model or settings.openai_config.model or "").strip(),
        timeout=int(timeout or getattr(settings.runtime, "agents_sdk_timeout", settings.openai_config.timeout) or settings.openai_config.timeout),
    )


def build_agents_sdk_model(
    *,
    api_base: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
    timeout: int | None = None,
) -> OpenAIChatCompletionsModel:
    model_config = _resolve_model_config(
        api_base=api_base,
        api_key=api_key,
        model=model,
        timeout=timeout,
    )
    client = AsyncOpenAI(
        api_key=model_config.api_key,
        base_url=model_config.api_base,
        timeout=model_config.timeout,
    )
    return OpenAIChatCompletionsModel(
        model=(
            str(getattr(settings.runtime, "agents_sdk_model", "") or "").strip()
            or model_config.model
        ),
        openai_client=client,
    )


def build_agents_sdk_model_settings() -> ModelSettings:
    return ModelSettings(
        temperature=0.35,
        parallel_tool_calls=False,
    )


def build_agents_sdk_run_config(*, workflow_name: str) -> RunConfig:
    return RunConfig(
        workflow_name=workflow_name,
        tracing_disabled=True,
    )
