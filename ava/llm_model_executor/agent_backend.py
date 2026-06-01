"""Agents SDK 执行后端。

该模块属于 `ava/inference_runtime` 正式实现的一部分，
负责在需要时使用 OpenAI Agents SDK 执行当前轮计划。

设计目标：
- 不再让 `ava/pipeline/agent` 承载正式实现
- 只消费新的 `TurnPlan` / `ConversationContext` / `user_message`
- 把会话播种、工具、管理器 agent、执行入口统一收敛到这里
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
import threading
from typing import Any, Callable

from agents import (
    Agent,
    ModelSettings,
    OpenAIChatCompletionsModel,
    RawResponsesStreamEvent,
    RunConfig,
    RunContextWrapper,
    RunItemStreamEvent,
    Runner,
    function_tool,
)
from openai import AsyncOpenAI
from openai.types.responses import ResponseTextDeltaEvent

from ava.domain.conversation.state import ConversationState
from ava.inference_runtime.types import TurnPlan
from ava.multi_turn_context_builder.types import ConversationContext
from ava.router_selector.schema import RouteDecision
from configs import BASE_DIR, settings

try:
    from agents import SessionABC, SessionSettings, TResponseInputItem
except Exception:  # pragma: no cover
    SessionABC = object  # type: ignore[assignment]
    SessionSettings = Any  # type: ignore[assignment]
    TResponseInputItem = Any  # type: ignore[assignment]

_SESSION_CONTAINER_KEY = "sessions"
_SESSION_LOCK = threading.RLock()


@dataclass(frozen=True)
class AgentsModelConfig:
    """Agents SDK 模型配置。"""

    api_base: str
    api_key: str
    model: str
    timeout: int


@dataclass
class AgentExecutionResult:
    """Agents SDK 执行结果。"""

    assistant_message: dict[str, Any]
    backend: str = "openai_agents_sdk"
    debug_events: list[dict[str, Any]] = field(default_factory=list)
    applied_patches: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class RuntimeAgentContext:
    """Agents SDK 本地运行时上下文。

    输入参数：
    - session_id: 当前会话标识
    - turn_id: 当前轮次编号
    - state: 对话状态对象
    - conversation_context: 当前轮可见的多轮上下文
    - decision: 路由结果
    - plan: 当前轮正式执行计划
    - user_message: 当前轮标准 user message
    - stop_event: 流式中断事件

    说明：
    - 该对象不会自动暴露给模型
    - 模型可见信息必须通过 instructions 或 tool 输出显式提供
    """

    session_id: str
    turn_id: int | None
    state: ConversationState
    conversation_context: ConversationContext
    decision: RouteDecision
    plan: TurnPlan
    user_message: dict[str, Any]
    stop_event: threading.Event | None = None
    pending_state_patches: list[dict[str, Any]] = field(default_factory=list)
    debug_events: list[dict[str, Any]] = field(default_factory=list)

    def add_patch(self, *, key: str, value: Any, reason: str) -> None:
        """记录待应用状态补丁。"""
        self.pending_state_patches.append(
            {
                "key": str(key or "").strip(),
                "value": value,
                "reason": str(reason or "").strip(),
            }
        )

    def add_event(self, name: str, payload: dict[str, Any] | None = None) -> None:
        """记录调试事件。"""
        self.debug_events.append(
            {
                "name": str(name or "").strip(),
                "payload": dict(payload or {}),
            }
        )


def _safe_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "model_dump") and callable(value.model_dump):
        return _json_safe(value.model_dump(mode="json"))
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return _json_safe(value.to_dict())
    return str(value)


def _resolve_model_config(
        *,
        api_base: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout: int | None = None,
) -> AgentsModelConfig:
    """解析 Agents SDK 模型配置。"""
    return AgentsModelConfig(
        api_base=str(api_base or settings.openai_config.api_base or "").strip(),
        api_key=str(api_key or settings.openai_config.api_key or "").strip(),
        model=str(model or settings.openai_config.model or "").strip(),
        timeout=int(
            timeout
            or getattr(settings.runtime, "agents_sdk_timeout", settings.openai_config.timeout)
            or settings.openai_config.timeout
        ),
    )


def _build_agents_sdk_model(
        *,
        api_base: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout: int | None = None,
) -> OpenAIChatCompletionsModel:
    """构建 Agents SDK 使用的模型对象。"""
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
        model=(str(getattr(settings.runtime, "agents_sdk_model", "") or "").strip() or model_config.model),
        openai_client=client,
    )


def _build_agents_sdk_model_settings() -> ModelSettings:
    """构建 Agents SDK 模型采样设置。"""
    return ModelSettings(
        temperature=0.35,
        parallel_tool_calls=False,
    )


def _build_agents_sdk_run_config(*, workflow_name: str) -> RunConfig:
    """构建 Agents SDK 运行配置。"""
    return RunConfig(
        workflow_name=workflow_name,
        tracing_disabled=True,
    )


def _resolve_session_db_path() -> Path:
    """解析 Agents SDK 会话存储文件路径。"""
    configured = Path(
        str(getattr(settings.runtime, "agents_sdk_session_db",
                    "state/agents_sessions.json") or "state/agents_sessions.json")
    )
    if configured.is_absolute():
        return configured
    return BASE_DIR / configured


class JsonFileSession(SessionABC):
    """基于 JSON 文件的轻量 Agents SDK Session 实现。"""

    def __init__(
            self,
            session_id: str,
            db_path: str | Path,
            session_settings: SessionSettings | None = None,
    ) -> None:
        self.session_id = session_id
        self.db_path = Path(db_path)
        self.session_settings = session_settings
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def _load_container(self) -> dict[str, Any]:
        if not self.db_path.exists():
            return {_SESSION_CONTAINER_KEY: {}}
        try:
            payload = json.loads(self.db_path.read_text(encoding="utf-8"))
        except Exception:
            return {_SESSION_CONTAINER_KEY: {}}
        if not isinstance(payload, dict):
            return {_SESSION_CONTAINER_KEY: {}}
        sessions = payload.get(_SESSION_CONTAINER_KEY)
        if isinstance(sessions, dict):
            return payload
        return {_SESSION_CONTAINER_KEY: {}}

    def _save_container(self, container: dict[str, Any]) -> None:
        self.db_path.write_text(json.dumps(container, ensure_ascii=False, indent=2), encoding="utf-8")

    def _session_items(self, container: dict[str, Any]) -> list[dict[str, Any]]:
        sessions = container.setdefault(_SESSION_CONTAINER_KEY, {})
        payload = sessions.setdefault(self.session_id, {"items": []})
        items = payload.setdefault("items", [])
        if isinstance(items, list):
            return items
        payload["items"] = []
        return payload["items"]

    async def get_items(self, limit: int | None = None) -> list[TResponseInputItem]:
        with _SESSION_LOCK:
            items = list(self._session_items(self._load_container()))
        effective_limit = limit if limit is not None else getattr(self.session_settings, "limit", None)
        if effective_limit is None or effective_limit <= 0:
            return items
        return items[-effective_limit:]

    async def add_items(self, items: list[TResponseInputItem]) -> None:
        if not items:
            return
        with _SESSION_LOCK:
            container = self._load_container()
            target = self._session_items(container)
            target.extend(_json_safe(item) for item in items)
            self._save_container(container)

    async def pop_item(self) -> TResponseInputItem | None:
        with _SESSION_LOCK:
            container = self._load_container()
            target = self._session_items(container)
            if not target:
                return None
            item = target.pop()
            self._save_container(container)
            return item

    async def clear_session(self) -> None:
        with _SESSION_LOCK:
            container = self._load_container()
            sessions = container.setdefault(_SESSION_CONTAINER_KEY, {})
            sessions[self.session_id] = {"items": []}
            self._save_container(container)


def build_agent_session(session_id: str) -> JsonFileSession:
    """构建当前会话对应的 Agents SDK session。"""
    return JsonFileSession(
        session_id=f"{session_id}:openai_agents_sdk",
        db_path=_resolve_session_db_path(),
    )


async def seed_agent_session_from_context(session: JsonFileSession, context: ConversationContext) -> None:
    """用当前多轮上下文播种 Agents SDK session。"""
    seed_items: list[dict[str, object]] = []
    for item in context.conversation:
        role = str(item.get("role", "") or "").strip()
        content = item.get("content", "")
        if role not in {"user", "assistant", "system"}:
            continue
        if isinstance(content, str):
            text = content.strip()
            if not text:
                continue
            seed_items.append({"role": role, "content": text})
            continue
        if isinstance(content, list) and content:
            seed_items.append({"role": role, "content": content})

    existing = [_json_safe(item) for item in await session.get_items()]
    if existing == seed_items:
        return

    await session.clear_session()
    if seed_items:
        await session.add_items(seed_items)


async def clear_agent_session_async(session_id: str) -> None:
    """异步清空指定会话的 Agents SDK session。"""
    session = build_agent_session(session_id)
    await session.clear_session()


def clear_agent_session(session_id: str) -> None:
    """同步清空指定会话的 Agents SDK session。"""
    asyncio.run(clear_agent_session_async(session_id))


@function_tool
def get_turn_plan(context: RunContextWrapper[RuntimeAgentContext]) -> str:
    """返回当前轮锁定后的路由与执行计划摘要。"""
    runtime = context.context
    prompt_package = runtime.plan.prompt_package
    payload = {
        "session_scene": runtime.decision.session_scene,
        "turn_scene": runtime.decision.turn_scene,
        "intent": runtime.decision.intent,
        "need_clarification": runtime.decision.need_clarification,
        "should_preserve_teaching_state": runtime.decision.should_preserve_teaching_state,
        "prompt_package": prompt_package.to_metadata() if prompt_package is not None else {},
        "active_skills": list(runtime.plan.active_skill_names),
        "router_plan": dict(runtime.plan.router_plan or {}),
    }
    runtime.add_event("tool.get_turn_plan", {"active_skills": list(runtime.plan.active_skill_names)})
    return _safe_json(payload)


@function_tool
def get_recent_history(context: RunContextWrapper[RuntimeAgentContext], limit: int = 8) -> str:
    """返回当前轮最近相关的多轮对话。"""
    runtime = context.context
    window = max(2, min(int(limit or 8), 12))
    history = runtime.conversation_context.conversation[-window:]
    runtime.add_event("tool.get_recent_history", {"limit": window, "items": len(history)})
    return _safe_json(history)


@function_tool
def get_reference_materials(context: RunContextWrapper[RuntimeAgentContext]) -> str:
    """返回当前用户消息中的非文本参考材料。"""
    runtime = context.context
    current_blocks = [
        dict(block)
        for block in list(runtime.conversation_context.current.user_message.get("content") or [])
        if isinstance(block, dict) and str(block.get("type", "") or "").strip() != "input_text"
    ]
    payload = {
        "current_artifacts": current_blocks,
        "reference_artifacts": [],
        "user_message": dict(runtime.conversation_context.current.user_message),
    }
    runtime.add_event(
        "tool.get_reference_materials",
        {
            "current_message_blocks": len(current_blocks),
            "reference_message_blocks": 0,
        },
    )
    return _safe_json(payload)


@function_tool
def note_state_patch(
        context: RunContextWrapper[RuntimeAgentContext],
        key: str,
        value: str,
        reason: str,
) -> str:
    """记录待应用的轻量连续性状态补丁。"""
    runtime = context.context
    runtime.add_patch(key=key, value=value, reason=reason)
    runtime.add_event(
        "tool.note_state_patch",
        {"key": str(key or "").strip(), "reason": str(reason or "").strip()},
    )
    return "已记录建议状态补丁，最终是否应用由运行时决定。"


def _manager_base_instructions(plan: TurnPlan) -> str:
    """获取当前轮管理器基础系统指令。"""
    return str(plan.instructions or "").strip()


def _build_manager_instructions(plan: TurnPlan):
    """构建管理器动态系统指令。"""
    base_prompt = _manager_base_instructions(plan)

    def _instructions(context, agent) -> str:
        runtime = context.context
        prompt_profile = dict(runtime.plan.prompt_profile)
        skill_names = list(runtime.plan.active_skill_names)
        locked = [
            f"session_scene={runtime.decision.session_scene}",
            f"turn_scene={runtime.decision.turn_scene}",
            f"intent={runtime.decision.intent}",
            f"capability={prompt_profile.get('capability') or '-'}",
            f"task={prompt_profile.get('task') or '-'}",
            f"knowledge={prompt_profile.get('knowledge') or '-'}",
            f"method={prompt_profile.get('method') or '-'}",
            f"audience={prompt_profile.get('audience') or '-'}",
            f"skills={','.join(skill_names) or '-'}",
        ]
        return (
                f"{base_prompt}\n\n"
                "你位于执行层，只负责把当前轮计划执行好。\n"
                "不要重新做路由，不要改写已锁定的 Skill 组合与当前轮计划。\n\n"
                "当前锁定信息：\n- " + "\n- ".join(locked) + "\n\n"
                                                            "执行要求：\n"
                                                            "- 先根据需要读取最近对话与参考材料。\n"
                                                            "- 如发现可更新的轻量教学状态，可调用 note_state_patch 提交建议。\n"
                                                            "- 最终直接回答用户，不暴露内部分析过程。"
        ).strip()

    return _instructions


def _history_specialist_instructions(context, agent) -> str:
    """构建历史恢复专家指令。"""
    return (
        "你是上下文恢复专家，不直接回答用户。\n"
        "请基于最近对话，提炼：\n"
        "1. 当前讨论对象\n"
        "2. 用户本轮核心诉求\n"
        "3. 是否延续上一轮\n"
        "4. 回答边界\n"
        "输出 4 条简洁要点。"
    )


def _message_block_specialist_instructions(context, agent) -> str:
    """构建参考材料阅读专家指令。"""
    return (
        "你是参考材料阅读专家，不直接回答用户。\n"
        "请提炼当前用户消息中的非文本材料里，与本轮回答最相关的信息。\n"
        "如果没有可用材料，请明确说明“无额外材料信息”。"
    )


def _prompt_package_specialist_instructions(context, agent) -> str:
    """构建 Skill 组合执行要点整理专家指令。"""
    runtime = context.context
    prompt_profile = dict(runtime.plan.prompt_profile)
    return (
        "你是执行计划整理专家，不直接回答用户。\n"
        "你不能改变已锁定的 capability/task/knowledge/method/audience 组合。\n"
        f"当前 capability={prompt_profile.get('capability') or '-'}\n"
        f"当前 task={prompt_profile.get('task') or '-'}\n"
        f"当前 knowledge={prompt_profile.get('knowledge') or '-'}\n"
        f"当前 method={prompt_profile.get('method') or '-'}\n"
        "请输出 3 到 5 条本轮回答执行要点。"
    )


def _has_non_text_blocks(context: ConversationContext) -> bool:
    """判断当前用户消息是否包含非文本内容块。"""
    return any(
        isinstance(block, dict) and str(block.get("type", "") or "").strip() != "input_text"
        for block in list(context.current.user_message.get("content") or [])
    )


def _build_manager_agent(
        plan: TurnPlan,
        context: ConversationContext,
        *,
        model_config: AgentsModelConfig | None = None,
) -> Agent[RuntimeAgentContext]:
    """构建当前轮执行管理器 agent。"""
    model = _build_agents_sdk_model(
        api_base=model_config.api_base if model_config is not None else None,
        api_key=model_config.api_key if model_config is not None else None,
        model=model_config.model if model_config is not None else None,
        timeout=model_config.timeout if model_config is not None else None,
    )
    model_settings = _build_agents_sdk_model_settings()
    nested_run_config = _build_agents_sdk_run_config(
        workflow_name=f"specialist:{_workflow_name(plan)}"
    )
    allow_specialists = not _has_non_text_blocks(context)

    history_specialist = Agent[RuntimeAgentContext](
        name="History Recovery Specialist",
        instructions=_history_specialist_instructions,
        tools=[get_turn_plan, get_recent_history],
        model=model,
        model_settings=model_settings,
    )
    message_block_specialist = Agent[RuntimeAgentContext](
        name="Message Block Reading Specialist",
        instructions=_message_block_specialist_instructions,
        tools=[get_reference_materials, get_turn_plan],
        model=model,
        model_settings=model_settings,
    )
    prompt_package_specialist = Agent[RuntimeAgentContext](
        name="Prompt Package Execution Specialist",
        instructions=_prompt_package_specialist_instructions,
        tools=[get_turn_plan, get_recent_history],
        model=model,
        model_settings=model_settings,
    )

    specialist_tools = (
        [
            history_specialist.as_tool(
                tool_name="recover_current_context",
                tool_description="恢复当前轮讨论对象、追问目标与连续性边界。",
                run_config=nested_run_config,
                max_turns=3,
            ),
            message_block_specialist.as_tool(
                tool_name="read_supporting_materials",
                tool_description="阅读当前用户消息中的参考材料，并提炼和本轮回答最相关的信息。",
                run_config=nested_run_config,
                max_turns=3,
            ),
            prompt_package_specialist.as_tool(
                tool_name="plan_response_under_locked_prompt_package",
                tool_description="在不改变既定 Skill 组合的前提下，整理当前轮回答执行要点。",
                run_config=nested_run_config,
                max_turns=3,
            ),
        ]
        if allow_specialists
        else []
    )

    return Agent[RuntimeAgentContext](
        name="AVA Execution Manager",
        instructions=_build_manager_instructions(plan),
        tools=[
            get_turn_plan,
            get_recent_history,
            get_reference_materials,
            note_state_patch,
            *specialist_tools,
        ],
        model=model,
        model_settings=model_settings,
    )


def _current_user_input(user_message: dict[str, Any]) -> str | list[dict[str, object]]:
    """把标准 user message 转成 Agents SDK 输入。"""
    content = list(user_message.get("content") or [])
    if not content:
        return ""
    return [{"role": "user", "content": content}]


def _apply_pending_state_patches(runtime: RuntimeAgentContext) -> list[dict[str, Any]]:
    """在成功结束后应用允许写入的轻量状态补丁。"""
    applied: list[dict[str, Any]] = []
    allowed_education_keys = {"knowledge_point", "stage", "last_problem", "level"}
    for patch in runtime.pending_state_patches:
        key = str(patch.get("key", "") or "").strip()
        value = str(patch.get("value", "") or "").strip()
        reason = str(patch.get("reason", "") or "").strip()
        if not key or not value:
            continue
        if key in allowed_education_keys:
            runtime.state.memory.set_education_state_value(key, value[:160])
            applied.append({"key": key, "value": value[:160], "reason": reason})
    return applied


def _timeout_seconds(timeout: int | None = None) -> int:
    """获取 Agents SDK 执行超时秒数。"""
    return int(
        timeout
        or getattr(settings.runtime, "agents_sdk_timeout", settings.openai_config.timeout)
        or settings.openai_config.timeout
    )


def _max_turns() -> int:
    """获取 Agents SDK 单次执行允许的内部轮次数。"""
    return int(getattr(settings.runtime, "agents_sdk_max_turns", 6) or 6)


def _workflow_name(plan: TurnPlan) -> str:
    """生成当前轮 Agents SDK 工作流名称。"""
    profile = dict(plan.prompt_profile)
    capability = str(profile.get("capability") or plan.decision.turn_scene or "unknown").strip() or "unknown"
    task = str(profile.get("task") or "default").strip() or "default"
    return f"AVA Agents SDK {capability}.{task}"


def _build_runtime_context(
        *,
        state: ConversationState,
        conversation_context: ConversationContext,
        decision: RouteDecision,
        plan: TurnPlan,
        user_message: dict[str, Any],
        current_turn_id: int | None,
        stop_event=None,
) -> RuntimeAgentContext:
    """构造 Agents SDK 本地运行时上下文。"""
    return RuntimeAgentContext(
        session_id=state.session_id,
        turn_id=current_turn_id,
        state=state,
        conversation_context=conversation_context,
        decision=decision,
        plan=plan,
        user_message=dict(user_message),
        stop_event=stop_event,
    )


async def _close_model_client(model: object) -> None:
    """关闭 Agents SDK 模型底层客户端。"""
    client = getattr(model, "_client", None)
    if client is None:
        return
    close = getattr(client, "close", None)
    if close is None:
        return
    result = close()
    if asyncio.iscoroutine(result):
        await result


class AgentBackend:
    """Agents SDK 执行后端。

    对外提供：
    - `run_sync(...)`
    - `run_stream(...)`
    - `clear_session(...)`
    """

    def run_sync(
            self,
            *,
            state: ConversationState,
            user_message: dict[str, Any],
            decision: RouteDecision,
            plan: TurnPlan,
            context: ConversationContext,
            api_base: str,
            api_key: str,
            model: str,
            timeout: int,
            current_turn_id: int | None = None,
    ) -> AgentExecutionResult:
        """同步执行当前轮计划。

        输入参数：
        - state: 会话状态
        - user_message: 当前轮标准用户消息
        - decision: 路由结果
        - plan: 当前轮执行计划
        - context: 当前轮多轮上下文
        - api_base/api_key/model/timeout: 模型执行参数
        - current_turn_id: 当前轮编号

        返回：
        - AgentExecutionResult: 包含回复文本、调试事件、应用的状态补丁
        """
        runtime = _build_runtime_context(
            state=state,
            conversation_context=context,
            decision=decision,
            plan=plan,
            user_message=user_message,
            current_turn_id=current_turn_id,
        )
        model_config = _resolve_model_config(
            api_base=api_base,
            api_key=api_key,
            model=model,
            timeout=timeout,
        )
        manager = _build_manager_agent(plan, context, model_config=model_config)
        session = build_agent_session(state.session_id)
        run_config = _build_agents_sdk_run_config(workflow_name=_workflow_name(plan))
        payload = _current_user_input(user_message)

        async def _run() -> Any:
            await seed_agent_session_from_context(session, context)
            try:
                return await asyncio.wait_for(
                    Runner.run(
                        manager,
                        payload,
                        context=runtime,
                        max_turns=_max_turns(),
                        run_config=run_config,
                        session=session,
                    ),
                    timeout=_timeout_seconds(timeout),
                )
            finally:
                await _close_model_client(manager.model)

        result = asyncio.run(_run())
        assistant_output_text = str(getattr(result, "final_output", "") or "").strip()
        if not assistant_output_text:
            assistant_output_text = str(result.final_output_as(str)).strip()
        if not assistant_output_text:
            raise RuntimeError("OpenAI Agents SDK returned empty final output.")

        applied_patches = _apply_pending_state_patches(runtime)
        return AgentExecutionResult(
            assistant_message={
                "role": "assistant",
                "content": (
                    [{"type": "output_text", "text": assistant_output_text}]
                    if str(assistant_output_text or "").strip()
                    else []
                ),
            },
            debug_events=runtime.debug_events,
            applied_patches=applied_patches,
        )

    def run_stream(
            self,
            *,
            state: ConversationState,
            user_message: dict[str, Any],
            decision: RouteDecision,
            plan: TurnPlan,
            context: ConversationContext,
            api_base: str,
            api_key: str,
            model: str,
            timeout: int,
            on_token: Callable[[str], None],
            current_turn_id: int | None = None,
            stop_event=None,
    ) -> AgentExecutionResult:
        """流式执行当前轮计划。

        输入参数：
        - state: 会话状态
        - user_message: 当前轮标准用户消息
        - decision: 路由结果
        - plan: 当前轮执行计划
        - context: 当前轮多轮上下文
        - api_base/api_key/model/timeout: 模型执行参数
        - on_token: 增量文本回调
        - current_turn_id: 当前轮编号
        - stop_event: 流式中断事件

        返回：
        - AgentExecutionResult: 包含回复文本、调试事件、应用的状态补丁
        """
        runtime = _build_runtime_context(
            state=state,
            conversation_context=context,
            decision=decision,
            plan=plan,
            user_message=user_message,
            current_turn_id=current_turn_id,
            stop_event=stop_event,
        )
        model_config = _resolve_model_config(
            api_base=api_base,
            api_key=api_key,
            model=model,
            timeout=timeout,
        )
        manager = _build_manager_agent(plan, context, model_config=model_config)
        session = build_agent_session(state.session_id)
        run_config = _build_agents_sdk_run_config(workflow_name=_workflow_name(plan))
        payload = _current_user_input(user_message)

        async def _run() -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
            text_parts: list[str] = []
            await seed_agent_session_from_context(session, context)
            stream = Runner.run_streamed(
                manager,
                payload,
                context=runtime,
                max_turns=_max_turns(),
                run_config=run_config,
                session=session,
            )
            try:
                async for event in stream.stream_events():
                    if stop_event is not None and stop_event.is_set():
                        stream.cancel()
                        runtime.add_event("stream.cancelled", {})
                        break
                    if isinstance(event, RawResponsesStreamEvent) and isinstance(event.data, ResponseTextDeltaEvent):
                        delta = str(event.data.delta or "")
                        if delta:
                            text_parts.append(delta)
                            on_token(delta)
                        continue
                    if isinstance(event, RunItemStreamEvent):
                        runtime.add_event(
                            f"run_item.{event.name}",
                            {"item_type": type(event.item).__name__},
                        )
                assistant_output_text = str(getattr(stream, "final_output", "") or "").strip() or "".join(text_parts).strip()
                if not assistant_output_text:
                    raise RuntimeError("OpenAI Agents SDK stream finished without final text.")
                if not text_parts and assistant_output_text:
                    on_token(assistant_output_text)
                applied_patches = _apply_pending_state_patches(runtime)
                return assistant_output_text, runtime.debug_events, applied_patches
            finally:
                await _close_model_client(manager.model)

        assistant_output_text, debug_events, applied_patches = asyncio.run(
            asyncio.wait_for(_run(), timeout=_timeout_seconds(timeout))
        )
        return AgentExecutionResult(
            assistant_message={
                "role": "assistant",
                "content": (
                    [{"type": "output_text", "text": assistant_output_text}]
                    if str(assistant_output_text or "").strip()
                    else []
                ),
            },
            debug_events=debug_events,
            applied_patches=applied_patches,
        )

