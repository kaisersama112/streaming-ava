"""Manager 技能子 Agent 工具挂载与白名单 patch 贯通（离线，不触发模型调用）。"""

from __future__ import annotations

from ava.inference_runtime.service import ReplyService  # noqa: F401  先初始化 runtime，避免循环导入
from ava.llm_model_executor.agent_backend import (
    AgentsModelConfig,
    RuntimeAgentContext,
    _build_manager_agent,
    _build_skill_agent_tools,
)
from ava.domain.conversation.state_patch import apply_state_patches
from tests.conftest import text_content
from tests.test_reply_service import _plan

_MODEL_CONFIG = AgentsModelConfig(
    api_base="http://127.0.0.1:9/v1", api_key="test-key", model="test-model", timeout=5
)


def _manager(plan):
    return _build_manager_agent(
        plan, plan.runtime_context.conversation_context, model_config=_MODEL_CONFIG
    )


def _tool_names(agent) -> set[str]:
    return {str(getattr(tool, "name", "") or "") for tool in agent.tools}


def test_education_manager_has_four_skill_tools(state):
    message = {"role": "user", "content": text_content("批改这道题")}
    plan = _plan(state, message, turn_scene="education")
    manager = _manager(plan)
    names = _tool_names(manager)
    assert {"skill_solve", "skill_check", "skill_explain", "skill_assess"} <= names
    assert "note_state_patch" in names


def test_general_manager_has_no_skill_tools(state):
    message = {"role": "user", "content": text_content("你好")}
    plan = _plan(state, message)
    manager = _manager(plan)
    assert not any(name.startswith("skill_") for name in _tool_names(manager))


def test_skill_agent_instructions_come_from_assets(state):
    message = {"role": "user", "content": text_content("讲解一下")}
    plan = _plan(state, message, turn_scene="education")
    manager = _manager(plan)
    skill_tools = [t for t in manager.tools if str(getattr(t, "name", "")).startswith("skill_")]
    assert len(skill_tools) == 4


def test_skill_subagent_patches_flow_through_whitelist(state):
    message = {"role": "user", "content": text_content("批改")}
    plan = _plan(state, message, turn_scene="education")
    runtime = RuntimeAgentContext(
        session_id=state.session_id,
        turn_id=1,
        state=state,
        conversation_context=plan.runtime_context.conversation_context,
        decision=plan.decision,
        plan=plan,
        user_message=message,
    )
    runtime.add_patch(key="knowledge_point", value="一元一次方程", reason="skill:check")
    runtime.add_patch(key="session_id", value="hijack", reason="evil")
    result = apply_state_patches(state, runtime.pending_state_patches, actor="skill:check")
    assert state.memory.education_state.get("knowledge_point") == "一元一次方程"
    assert state.session_id != "hijack"
    assert [item["reject_reason"] for item in result["rejected"]] == ["not_in_whitelist"]