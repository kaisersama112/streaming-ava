"""状态白名单 patch 机制测试。"""

from __future__ import annotations

from ava.domain.conversation.state_patch import (
    AGENT_PATCH_WHITELIST,
    apply_state_patches,
)


def test_whitelist_applies_education_keys(state):
    result = apply_state_patches(
        state,
        [
            {"key": "knowledge_point", "value": "一元二次方程", "reason": "本轮讲解主题"},
            {"key": "subject", "value": "math"},
        ],
        actor="solve_agent",
    )
    assert [item["key"] for item in result["applied"]] == ["knowledge_point", "subject"]
    assert not result["rejected"]
    assert state.memory.education_state["knowledge_point"] == "一元二次方程"


def test_non_whitelisted_keys_rejected(state):
    result = apply_state_patches(
        state,
        [
            {"key": "session_id", "value": "hacked"},
            {"key": "turn_records", "value": []},
            {"key": "responder_previous_response_id", "value": "resp_x"},
            {"key": "api_key", "value": "sk-leak"},
        ],
    )
    assert not result["applied"]
    assert len(result["rejected"]) == 4
    assert all(item["reject_reason"] == "not_in_whitelist" for item in result["rejected"])
    assert state.session_id == "test-session"
    assert state.turn_records == []


def test_user_facts_and_topic_hint(state):
    result = apply_state_patches(
        state,
        [
            {"key": "user_facts", "value": {"grade": "初二", "name": "小明"}},
            {"key": "recent_topic_hint", "value": "函数图像"},
        ],
    )
    assert len(result["applied"]) == 2
    assert state.memory.user_facts["grade"] == "初二"
    assert "函数图像" in state.memory.recent_topics


def test_invalid_values_rejected(state):
    result = apply_state_patches(
        state,
        [
            {"key": "subject", "value": ""},
            {"key": "learning_objects", "value": {"bad": 1}},
            {"key": "user_facts", "value": "not-a-dict"},
        ],
    )
    assert not result["applied"]
    assert all(item["reject_reason"] == "invalid_value" for item in result["rejected"])


def test_long_values_truncated(state):
    apply_state_patches(state, [{"key": "last_problem", "value": "x" * 500}])
    assert len(state.memory.education_state["last_problem"]["text"]) <= 160


def test_whitelist_is_frozen():
    assert "session_id" not in AGENT_PATCH_WHITELIST
    assert "knowledge_point" in AGENT_PATCH_WHITELIST