"""基于 OpenAI Agents SDK 的技能子 Agent 执行器。"""

from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass, field
from typing import Any

from agents import (
    Agent,
    ModelSettings,
    OpenAIChatCompletionsModel,
    RunConfig,
    RunContextWrapper,
    Runner,
    function_tool,
)
import httpx
from openai import AsyncOpenAI

from ava.core.tracing import trace_event
from ava.domain.conversation.state_patch import AGENT_PATCH_WHITELIST
from ava.domain.multimodal.continuity import ARTIFACT_BLOCK_TYPES
from configs import settings

from . import tracing_setup  # noqa: F401  安装无导出 trace provider，须在 Runner.run 前生效
from .skills import build_subagent_instructions
from .types import IntentItem, SubAgentResult


@dataclass
class SkillRunContext:
    """子 Agent 运行期上下文（不直接暴露给模型）。"""

    session_id: str = ""
    turn_id: int | None = None
    trace_id: str = ""
    skill: str = ""
    task_id: str = ""
    runtime_section: str = ""
    patches: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)


@function_tool
def note_state_patch(ctx: RunContextWrapper[SkillRunContext], key: str, value: str, reason: str) -> str:
    """提交一条会话状态更新建议（只有白名单字段会被采纳）。"""
    normalized_key = str(key or "").strip()
    run_ctx = ctx.context
    if normalized_key not in AGENT_PATCH_WHITELIST:
        run_ctx.events.append({"name": "state.patch.rejected", "key": normalized_key})
        return f"rejected: {normalized_key} 不在白名单内，未写入。"
    run_ctx.patches.append(
        {
            "key": normalized_key,
            "value": str(value or "").strip()[:160],
            "reason": str(reason or "").strip()[:160],
            "actor": f"skill:{run_ctx.skill}",
            "turn_id": run_ctx.turn_id,
        }
    )
    return f"accepted: {normalized_key} 已记录为待应用建议。"


@function_tool
def get_runtime_facts(ctx: RunContextWrapper[SkillRunContext]) -> str:
    """读取当前轮只读运行时事实（教育状态、附件摘要、视觉连续性）。"""
    return ctx.context.runtime_section or "无运行时事实。"


def _skill_input(user_message: dict[str, Any], task: IntentItem) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = []
    for block in list((user_message or {}).get("content") or []):
        if not isinstance(block, dict):
            continue
        block_type = str(block.get("type", "") or "").strip()
        if block_type in ARTIFACT_BLOCK_TYPES and block_type != "input_image":
            content.append({"type": "input_text", "text": f"[{block_type} 附件，见运行时事实摘要]"})
        else:
            content.append(block)
    directive = f"【子任务】技能={task.skill}；参数={task.params or {}}"
    content.append({"type": "input_text", "text": directive})
    return [{"role": "user", "content": content}]


class AgentsSDKSkillRunner:
    """用 Agents SDK 执行单个技能子任务。"""

    def __init__(self, *, prompt_center: Any = None, model: str = "", timeout: int | None = None) -> None:
        self.prompt_center = prompt_center
        self.model = str(model or "").strip()
        self.timeout = timeout

    def _client(self, task: IntentItem) -> AsyncOpenAI:
        api_base = str(task.params.get("api_base") or settings.openai_config.api_base or "").strip()
        api_key = str(task.params.get("api_key") or settings.openai_config.api_key or "").strip()
        kwargs: dict[str, Any] = {"api_key": api_key or "missing-key"}
        if api_base:
            kwargs["base_url"] = api_base
        kwargs["http_client"] = httpx.AsyncClient(trust_env=False, timeout=60.0)
        return AsyncOpenAI(**kwargs)

    def __call__(
        self,
        task: IntentItem,
        ctx: Any,
        *,
        stop_event: threading.Event | None = None,
    ) -> SubAgentResult:
        run_ctx = SkillRunContext(
            session_id=ctx.session_id,
            turn_id=ctx.turn_id,
            trace_id=ctx.trace_id,
            skill=task.skill,
            task_id=task.task_id,
            runtime_section=ctx.runtime_section,
        )
        model_name = str(task.params.get("model") or self.model or settings.openai_config.model or "").strip()
        agent = Agent[SkillRunContext](
            name=f"skill_{task.skill.replace('-', '_')}",
            instructions=build_subagent_instructions(
                self.prompt_center,
                task.skill,
                runtime_section=ctx.runtime_section,
            ),
            tools=[note_state_patch, get_runtime_facts],
            model=OpenAIChatCompletionsModel(model=model_name, openai_client=self._client(task)),
            model_settings=ModelSettings(temperature=0.3, parallel_tool_calls=False),
        )
        timeout_seconds = int(
            self.timeout
            or getattr(settings.runtime, "agents_sdk_timeout", 0)
            or settings.openai_config.timeout
            or 60
        )

        async def _run() -> Any:
            return await asyncio.wait_for(
                Runner.run(
                    agent,
                    input=_skill_input(ctx.user_message, task),
                    context=run_ctx,
                    max_turns=int(getattr(settings.runtime, "agents_sdk_max_turns", 4) or 4),
                    # SDK 自带 trace 导出器会构造 trust_env httpx 客户端，Windows 非法注册表代理会使其崩溃
                    run_config=RunConfig(workflow_name=f"skill:{task.skill}", tracing_disabled=True),
                ),
                timeout=timeout_seconds,
            )

        async def _run_with_cancel() -> Any:
            runner_task = asyncio.create_task(_run())
            while not runner_task.done():
                if stop_event is not None and stop_event.is_set():
                    runner_task.cancel()
                    raise asyncio.CancelledError()
                await asyncio.sleep(0.05)
            return runner_task.result()

        try:
            result = asyncio.run(_run_with_cancel())
        except asyncio.CancelledError:
            return SubAgentResult(
                task_id=task.task_id,
                skill=task.skill,
                status="cancelled",
                patches=list(run_ctx.patches),
                events=list(run_ctx.events),
            )
        except Exception as exc:
            logging.getLogger(__name__).exception("skill %s failed", task.skill)
            trace_event(
                "agent.skill.error",
                actor=f"skill:{task.skill}",
                session_id=ctx.session_id,
                turn_id=ctx.turn_id,
                trace_id=ctx.trace_id,
                error=f"{type(exc).__name__}: {exc}"[:300],
            )
            return SubAgentResult(
                task_id=task.task_id,
                skill=task.skill,
                status="error",
                error=f"{type(exc).__name__}: {exc}"[:300],
                patches=list(run_ctx.patches),
                events=list(run_ctx.events),
            )
        text = str(getattr(result, "final_output", "") or "").strip()
        return SubAgentResult(
            task_id=task.task_id,
            skill=task.skill,
            status="ok",
            text=text,
            patches=list(run_ctx.patches),
            events=list(run_ctx.events),
        )