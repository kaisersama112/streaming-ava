"""Agents SDK 管理器与辅助输入装配。"""

from __future__ import annotations

from typing import Any

from agents import Agent

from ava.inference_runtime.types import TurnPlan
from ava.multi_turn_context_builder.types import ConversationContext

from .context import AvaAgentContext
from .model_factory import (
    AgentsModelConfig,
    build_agents_sdk_model,
    build_agents_sdk_model_settings,
    build_agents_sdk_run_config,
)
from .tools import (
    get_recent_history,
    get_reference_materials,
    get_turn_plan,
    note_state_patch,
)


def _first_system_message(plan: TurnPlan) -> str:
    """从新计划中的 `instructions` 直接读取系统指令。"""
    return str(plan.instructions or "").strip()


def _manager_instructions(plan: TurnPlan):
    """构造管理器动态指令。

    上游已经完成：
    - 路由判定
    - 策略选择
    - responder instructions 编译

    因此这里不再重复做策略规划，只强调执行边界。
    """

    base_prompt = _first_system_message(plan)

    def _instructions(context, agent) -> str:
        runtime = context.context
        locked = [
            f"session_scene={runtime.decision.session_scene}",
            f"turn_scene={runtime.decision.turn_scene}",
            f"intent={runtime.decision.intent}",
            f"strategy_id={runtime.strategy.strategy_id}",
            f"branch={runtime.strategy.branch}",
            f"mode={runtime.strategy.mode or '-'}",
            f"module={runtime.strategy.module or '-'}",
            f"subject={runtime.strategy.subject or '-'}",
            f"pedagogy={runtime.strategy.pedagogy or '-'}",
            f"policy_id={runtime.strategy.policy_id or '-'}",
        ]
        return (
            f"{base_prompt}\n\n"
            "你位于执行层，只负责把当前轮计划执行好。\n"
            "不要重新做路由，不要改写已锁定策略。\n\n"
            "当前锁定信息：\n- " + "\n- ".join(locked) + "\n\n"
            "执行要求：\n"
            "- 先根据需要读取最近对话与参考材料。\n"
            "- 如发现可更新的轻量教学状态，可调用 note_state_patch 提交建议。\n"
            "- 最终直接回答用户，不暴露内部分析过程。"
        ).strip()

    return _instructions


def _history_specialist_instructions(context, agent) -> str:
    return (
        "你是上下文恢复专家，不直接回答用户。\n"
        "请基于最近对话，提炼：\n"
        "1. 当前讨论对象\n"
        "2. 用户本轮核心诉求\n"
        "3. 是否延续上一轮\n"
        "4. 回答边界\n"
        "输出 4 条简洁要点。"
    )


def _artifact_specialist_instructions(context, agent) -> str:
    return (
        "你是参考材料阅读专家，不直接回答用户。\n"
        "请提炼当前用户消息中的非文本材料里，与本轮回答最相关的信息。\n"
        "如果没有可用材料，请明确说明“无额外材料信息”。"
    )


def _strategy_specialist_instructions(context, agent) -> str:
    runtime = context.context
    return (
        "你是执行计划整理专家，不直接回答用户。\n"
        "你不能改变已锁定的 branch/module/subject/pedagogy/mode。\n"
        f"当前 strategy_id={runtime.strategy.strategy_id}\n"
        "请输出 3 到 5 条本轮回答执行要点。"
    )


def _has_non_text_blocks(context: ConversationContext) -> bool:
    return any(
        isinstance(block, dict) and str(block.get("type", "") or "").strip() != "input_text"
        for block in list(context.current.user_message.get("content") or [])
    )


def build_manager_agent(
    plan: TurnPlan,
    context: ConversationContext,
    *,
    model_config: AgentsModelConfig | None = None,
) -> Agent[AvaAgentContext]:
    """构造执行管理器。"""
    model = build_agents_sdk_model(
        api_base=model_config.api_base if model_config is not None else None,
        api_key=model_config.api_key if model_config is not None else None,
        model=model_config.model if model_config is not None else None,
        timeout=model_config.timeout if model_config is not None else None,
    )
    model_settings = build_agents_sdk_model_settings()
    nested_run_config = build_agents_sdk_run_config(workflow_name=f"specialist:{getattr(plan.strategy, 'strategy_id', 'unknown')}")
    allow_specialists = not _has_non_text_blocks(context)

    history_specialist = Agent[AvaAgentContext](
        name="History Recovery Specialist",
        instructions=_history_specialist_instructions,
        tools=[get_turn_plan, get_recent_history],
        model=model,
        model_settings=model_settings,
    )
    artifact_specialist = Agent[AvaAgentContext](
        name="Artifact Reading Specialist",
        instructions=_artifact_specialist_instructions,
        tools=[get_reference_materials, get_turn_plan],
        model=model,
        model_settings=model_settings,
    )
    strategy_specialist = Agent[AvaAgentContext](
        name="Strategy Execution Specialist",
        instructions=_strategy_specialist_instructions,
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
            artifact_specialist.as_tool(
                tool_name="read_supporting_materials",
                tool_description="阅读当前用户消息中的参考材料，并提炼和本轮回答最相关的信息。",
                run_config=nested_run_config,
                max_turns=3,
            ),
            strategy_specialist.as_tool(
                tool_name="plan_response_under_locked_strategy",
                tool_description="在不改变既定策略的前提下，整理当前轮回答执行要点。",
                run_config=nested_run_config,
                max_turns=3,
            ),
        ]
        if allow_specialists
        else []
    )

    return Agent[AvaAgentContext](
        name="AVA Execution Manager",
        instructions=_manager_instructions(plan),
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


def current_user_input(user_message: dict[str, Any]) -> str | list[dict[str, object]]:
    """把标准 user message 转成 Agents SDK 运行输入。"""
    content = list(user_message.get("content") or [])
    if not content:
        return ""
    return [{"role": "user", "content": content}]
