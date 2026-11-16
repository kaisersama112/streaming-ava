"""统一 trace schema 测试。"""

from __future__ import annotations

import json

from ava.core.tracing import append_trace_log, new_trace_id, record_turn_evaluation, trace_event


def test_trace_schema_fields(tmp_path):
    log = tmp_path / "trace.jsonl"
    record = append_trace_log(
        {
            "event": "route.decision",
            "actor": "router",
            "session_id": "s1",
            "turn_id": 3,
            "trace_id": "abc",
            "latency_ms": 12.5,
            "confidence": 0.9,
        },
        log_file=str(log),
    )
    assert set(record) >= {"ts", "event", "actor", "session_id", "turn_id", "trace_id", "latency_ms", "payload"}
    assert record["payload"]["confidence"] == 0.9
    lines = log.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["event"] == "route.decision"


def test_trace_event_helper(tmp_path):
    log = tmp_path / "trace.jsonl"
    record = trace_event(
        "model.selected", actor="runtime", session_id="s1", turn_id=1, tier="small", log_file=str(log)
    )
    assert record["event"] == "model.selected"
    assert record["payload"]["tier"] == "small"
    assert json.loads(log.read_text(encoding="utf-8").strip())["payload"]["tier"] == "small"


def test_trace_id_unique():
    assert new_trace_id() != new_trace_id()
    assert len(new_trace_id()) == 16


def test_record_turn_evaluation(tmp_path, monkeypatch):
    from configs import settings

    log = tmp_path / "evaluation.jsonl"
    monkeypatch.setattr(settings.runtime, "evaluation_log_file", str(log))
    record = record_turn_evaluation(
        session_id="s1",
        turn_id=2,
        trace_id="t2",
        evaluation={"turn_result": "completed", "scene": "education"},
        decision={"intent": "check", "confidence": 0.93},
        reply_debug={
            "model_selection": {"tier": "large", "model": "stub"},
            "orchestration": {
                "mode": "conditional",
                "results": [{"skill": "check", "status": "ok", "latency_ms": 300}],
                "latency_ms": 620,
            },
            "applied_state_patches": [{"key": "knowledge_point"}],
            "rejected_state_patches": [{"key": "core_state"}],
        },
        timeline_ms={"t2_router_done": 210.0, "t4_first_token": 900.0},
    )
    assert record["patches"] == {"applied": 1, "rejected": 1}
    assert record["orchestration"]["skills"][0]["skill"] == "check"
    saved = json.loads(log.read_text(encoding="utf-8").strip())
    assert saved["evaluation"]["turn_result"] == "completed"
    assert saved["decision"]["intent"] == "check"
    assert saved["model_selection"]["tier"] == "large"
    assert saved["timeline_ms"]["t4_first_token"] == 900.0