"""PipelineDebugEvent 序列化合同测试。"""

from ava.core.events.realtime import PipelineDebugEvent, RealtimeEventBus


def test_pipeline_debug_event_payload():
    event = PipelineDebugEvent(
        backend="skill_orchestrator",
        model_selection={"tier": "small", "model": "qwen3-4b", "reason": "low_complexity"},
        applied_state_patches=[{"key": "knowledge_point", "value": "分数加法", "actor": "skill_check"}],
        rejected_state_patches=[{"key": "session_id", "reason": "not_in_whitelist"}],
        orchestration={"mode": "serial", "results": [{"skill": "check", "status": "ok"}]},
        agent_debug_events=[{"event": "tool_call", "tool": "get_turn_plan"}],
        turn_id=7,
    )
    payload = event.to_payload()
    assert payload["type"] == "debug_pipeline"
    assert payload["turn_id"] == 7
    assert payload["backend"] == "skill_orchestrator"
    assert payload["model_selection"]["tier"] == "small"
    assert payload["applied_state_patches"][0]["key"] == "knowledge_point"
    assert payload["rejected_state_patches"][0]["reason"] == "not_in_whitelist"
    assert payload["orchestration"]["mode"] == "serial"
    assert payload["agent_debug_events"][0]["tool"] == "get_turn_plan"


def test_pipeline_debug_event_defaults_and_bus_roundtrip():
    bus = RealtimeEventBus()
    bus.publish(PipelineDebugEvent(turn_id=1))
    drained = bus.drain()
    assert len(drained) == 1
    payload = drained[0].to_payload()
    assert payload["type"] == "debug_pipeline"
    assert payload["backend"] == ""
    assert payload["model_selection"] == {}
    assert payload["applied_state_patches"] == []
    assert payload["rejected_state_patches"] == []
    assert payload["orchestration"] == {}
    assert payload["agent_debug_events"] == []