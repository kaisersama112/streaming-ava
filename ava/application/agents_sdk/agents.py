"""Agent builders for execution-layer specialists."""

from __future__ import annotations

from typing import Any

from agents import Agent

from ava.application.orchestration.types import TurnPlan
from ava.domain.context import ContextSnapshot, TurnInput

from .context import AvaAgentContext
from .model_factory import (
    AgentsModelConfig,
    build_agents_sdk_model,
    build_agents_sdk_model_settings,
    build_agents_sdk_run_config,
)
from .tools import (
    get_education_state,
    get_recent_history,
    get_reference_materials,
    get_turn_plan,
    note_state_patch,
)


def _message_content_to_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                text = str(block.get("text", "")).strip()
                if text:
                    parts.append(text)
        return "\n".join(parts).strip()
    return str(content or "")


def _base_system_prompt(plan: TurnPlan) -> str:
    if not plan.responder_messages:
        return ""
    first = plan.responder_messages[0]
    if str(first.get("role", "")).strip() != "system":
        return ""
    return _message_content_to_text(first.get("content", ""))


def _manager_instructions(plan: TurnPlan):
    base_prompt = _base_system_prompt(plan)

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
            f"style={runtime.strategy.style or '-'}",
            f"policy_id={runtime.strategy.policy_id or '-'}",
        ]
        branch_guidance = "当前是通用执行分支。"
        if runtime.strategy.branch == "education":
            analysis = dict(runtime.strategy.analysis or {})
            branch_guidance = (
                "当前是教育执行分支。你必须严格遵守上游已经选定的教学边界，不要擅自改 module/subject/style。"
                f"\nprimary_action={analysis.get('primary_action', '')}"
                f"\nprimary_scenario={analysis.get('primary_scenario', '')}"
                f"\nanswer_boundary={analysis.get('answer_boundary', '')}"
            )
        return (
            f"{base_prompt}\n\n"
            "你正在一个由上游 Router 驱动的执行层中工作。\n"
            "上游已经完成当前轮意图识别和资产选择，你不能重新做场景改写，只能把已选计划执行好。\n"
            f"{branch_guidance}\n"
            "当前锁定计划：\n- " + "\n- ".join(locked) + "\n\n"
            "工作方式：\n"
            "- 如果当前输入或继承上下文里已经带了图片，你可以直接使用这些图片，不要要求用户重复上传。\n"
            "- 先按需调用工具恢复最近历史、计划边界和参考素材。\n"
            "- 需要额外分析时，可调用 specialists 作为 tools。\n"
            "- 最终直接向用户回答，不要暴露内部工具、JSON 或分析链路。\n"
            "- 如果你发现某个轻量教育状态值得更新，可调用 note_state_patch 提建议。\n"
        ).strip()

    return _instructions


def _history_specialist_instructions(context, agent) -> str:
    runtime = context.context
    return (
        "你是上下文恢复专家，不直接回答用户。\n"
        "你的任务是根据最近几轮问答、当前用户输入和已锁定策略，恢复：\n"
        "1. 当前讨论对象是什么\n"
        "2. 这一轮用户真正想问什么\n"
        "3. 这一轮是否在延续前几轮对象\n"
        "4. 回答时最该注意的边界\n\n"
        f"当前 strategy_id={runtime.strategy.strategy_id}\n"
        "输出 4 个简短要点，不要长篇回答。"
    )


def _artifact_specialist_instructions(context, agent) -> str:
    return (
        "你是素材阅读专家，不直接回答用户。\n"
        "如果存在当前附件或继承参考附件，请提炼出与本轮回答最相关的信息。\n"
        "如果没有可用素材，明确说明“无额外素材信息”。\n"
        "输出尽量短，只保留最终回答真正需要的材料。"
    )


def _strategy_specialist_instructions(context, agent) -> str:
    runtime = context.context
    return (
        "你是回答策略执行专家，不直接回答用户。\n"
        "你不能改写上游已锁定的 branch/module/subject/style/mode。\n"
        "你的任务是把当前 strategy 转成一个清晰的回答计划，包括：\n"
        "1. 这轮应先做什么\n"
        "2. 应该直接答、提示、核对还是解释\n"
        "3. 哪些点必须说，哪些点不要扩展\n\n"
        f"当前 strategy_id={runtime.strategy.strategy_id}\n"
        "输出 3 到 5 个要点。"
    )


def _has_multimodal_context(snapshot: ContextSnapshot) -> bool:
    return bool(snapshot.artifacts or snapshot.reference_artifacts)


def build_manager_agent(
    plan: TurnPlan,
    snapshot: ContextSnapshot,
    *,
    model_config: AgentsModelConfig | None = None,
) -> Agent[AvaAgentContext]:
    model = build_agents_sdk_model(
        snapshot,
        api_base=model_config.api_base if model_config is not None else None,
        api_key=model_config.api_key if model_config is not None else None,
        model=model_config.model if model_config is not None else None,
        multimodal_model=model_config.multimodal_model if model_config is not None else None,
        timeout=model_config.timeout if model_config is not None else None,
    )
    model_settings = build_agents_sdk_model_settings()
    nested_run_config = build_agents_sdk_run_config(workflow_name=f"specialist:{plan.strategy.strategy_id}")
    allow_specialists = not _has_multimodal_context(snapshot)

    history_specialist = Agent[AvaAgentContext](
        name="History Recovery Specialist",
        instructions=_history_specialist_instructions,
        tools=[get_turn_plan, get_recent_history, get_education_state],
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
        tools=[get_turn_plan, get_recent_history, get_education_state],
        model=model,
        model_settings=model_settings,
    )

    specialist_tools = [
        *(
            [
                history_specialist.as_tool(
                    tool_name="recover_current_context",
                    tool_description="恢复当前轮真正的讨论对象、追问目标和连续性边界。",
                    run_config=nested_run_config,
                    max_turns=3,
                ),
                artifact_specialist.as_tool(
                    tool_name="read_supporting_materials",
                    tool_description="阅读当前或继承的参考素材，并提炼出与本轮回答最相关的信息。",
                    run_config=nested_run_config,
                    max_turns=3,
                ),
                strategy_specialist.as_tool(
                    tool_name="plan_response_under_locked_strategy",
                    tool_description="在不改变既定 strategy 的前提下，生成本轮回答计划。",
                    run_config=nested_run_config,
                    max_turns=3,
                ),
            ]
            if allow_specialists
            else []
        ),
    ]

    return Agent[AvaAgentContext](
        name="AVA Execution Manager",
        instructions=_manager_instructions(plan),
        tools=[
            get_turn_plan,
            get_recent_history,
            get_reference_materials,
            get_education_state,
            note_state_patch,
            *specialist_tools,
        ],
        model=model,
        model_settings=model_settings,
    )


def _normalize_sdk_content_blocks(content: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        block_type = str(block.get("type", "")).strip()
        if block_type == "text":
            text = str(block.get("text", "") or "").strip()
            if text:
                normalized.append({"type": "input_text", "text": text})
            continue
        if block_type == "input_text":
            text = str(block.get("text", "") or "").strip()
            if text:
                normalized.append({"type": "input_text", "text": text})
            continue
        if block_type == "image_url":
            image_payload = block.get("image_url")
            if isinstance(image_payload, dict):
                image_url = str(image_payload.get("url", "") or "").strip()
                if image_url:
                    normalized.append({"type": "input_image", "image_url": image_url})
            continue
        if block_type == "input_image":
            image_url = str(block.get("image_url", "") or "").strip()
            if image_url:
                normalized.append({"type": "input_image", "image_url": image_url})
    return normalized


def current_user_input(plan: TurnPlan, turn_input: TurnInput) -> str | list[dict[str, object]]:
    for message in reversed(plan.responder_messages):
        if str(message.get("role", "")).strip() == "user":
            content = message.get("content", "")
            if isinstance(content, str):
                text = content.strip()
                if text:
                    return text
            if isinstance(content, list):
                normalized = _normalize_sdk_content_blocks(content)
                if normalized:
                    return [{"role": "user", "content": normalized}]
                text = _message_content_to_text(content).strip()
                if text:
                    return text
    return (turn_input.normalized_text() or turn_input.multimodal_summary() or "").strip()
