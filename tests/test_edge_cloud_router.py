"""端云协同路由：端侧优先 / 云兜底 / 指纹缓存 / 并行预取。"""

from __future__ import annotations

import json
import time

import pytest

from ava.llm_model_executor.types import InferenceResult
from ava.router_selector.service import RouterService
from configs import settings
from tests.conftest import text_content


def _route_json(confidence=0.9, turn_scene="education", intent="solve"):
    return json.dumps(
        {
            "session_scene": "education" if turn_scene == "education" else "general",
            "turn_scene": turn_scene,
            "intent": intent,
            "confidence": confidence,
            "need_clarification": False,
            "should_preserve_teaching_state": turn_scene == "education",
            "plan": {"module": intent},
        },
        ensure_ascii=False,
    )


class StubRouterLLM:
    def __init__(self, *, edge_text=None, edge_error=False, cloud_text=None, delay=0.0):
        self.edge_text = edge_text if edge_text is not None else _route_json(0.9)
        self.cloud_text = cloud_text if cloud_text is not None else _route_json(0.95)
        self.edge_error = edge_error
        self.delay = delay
        self.calls = []

    def route(self, context):
        self.calls.append(context)
        if self.delay:
            time.sleep(self.delay)
        if context.model == "qwen3-4b-router":
            if self.edge_error:
                raise TimeoutError("edge timeout")
            return InferenceResult(text=self.edge_text)
        return InferenceResult(text=self.cloud_text)


@pytest.fixture(autouse=True)
def _flags(monkeypatch):
    monkeypatch.setattr(settings.runtime, "trace_enabled", False, raising=False)
    monkeypatch.setattr(settings.runtime, "route_cache_enabled", False, raising=False)
    monkeypatch.setattr(settings.runtime, "parallel_prefetch_enabled", False, raising=False)
    monkeypatch.setattr(settings.intent_config, "enabled", False, raising=False)
    monkeypatch.setattr(settings.intent_config, "provider", "api", raising=False)
    monkeypatch.setattr(settings.intent_config, "cloud_fallback_enabled", True, raising=False)
    monkeypatch.setattr(settings.intent_config, "min_confidence", 0.6, raising=False)


def _service(llm, prompt_center):
    return RouterService(prompt_center=prompt_center, llm_service=llm)


def _route(service, state, text="解这道方程"):
    return service.route(
        user_message={"role": "user", "content": text_content(text)},
        state=state,
        history_window=4,
    )


def test_cloud_only_by_default(state, prompt_center):
    llm = StubRouterLLM()
    result = _route(_service(llm, prompt_center), state)
    assert result.selection_summary["provider"] == "cloud"
    assert len(llm.calls) == 1


def test_edge_local_success(state, prompt_center, monkeypatch):
    monkeypatch.setattr(settings.intent_config, "enabled", True, raising=False)
    monkeypatch.setattr(settings.intent_config, "provider", "local", raising=False)
    llm = StubRouterLLM()
    result = _route(_service(llm, prompt_center), state)
    assert result.selection_summary["provider"] == "edge_local"
    assert result.selection_summary["model"] == "qwen3-4b-router"
    edge_call = llm.calls[0]
    assert edge_call.metadata["api_base"] == "http://127.0.0.1:8080/v1"
    assert edge_call.metadata["timeout"] == pytest.approx(0.7)
    last_text = json.dumps(edge_call.input[-1], ensure_ascii=False)
    assert "/no_think" in last_text
    assert len(llm.calls) == 1


def test_edge_low_confidence_falls_back_to_cloud(state, prompt_center, monkeypatch):
    monkeypatch.setattr(settings.intent_config, "enabled", True, raising=False)
    monkeypatch.setattr(settings.intent_config, "provider", "local", raising=False)
    llm = StubRouterLLM(edge_text=_route_json(0.3))
    result = _route(_service(llm, prompt_center), state)
    assert result.selection_summary["provider"] == "cloud"
    assert len(llm.calls) == 2
    assert result.decision.confidence == pytest.approx(0.95)


def test_edge_error_falls_back_to_cloud(state, prompt_center, monkeypatch):
    monkeypatch.setattr(settings.intent_config, "enabled", True, raising=False)
    monkeypatch.setattr(settings.intent_config, "provider", "local", raising=False)
    llm = StubRouterLLM(edge_error=True)
    result = _route(_service(llm, prompt_center), state)
    assert result.selection_summary["provider"] == "cloud"
    assert len(llm.calls) == 2


def test_edge_error_without_fallback_raises(state, prompt_center, monkeypatch):
    monkeypatch.setattr(settings.intent_config, "enabled", True, raising=False)
    monkeypatch.setattr(settings.intent_config, "provider", "local", raising=False)
    monkeypatch.setattr(settings.intent_config, "cloud_fallback_enabled", False, raising=False)
    llm = StubRouterLLM(edge_error=True)
    with pytest.raises(RuntimeError, match="cloud fallback disabled"):
        _route(_service(llm, prompt_center), state)


def test_route_cache_hit_skips_model(state, prompt_center, monkeypatch):
    monkeypatch.setattr(settings.runtime, "route_cache_enabled", True, raising=False)
    llm = StubRouterLLM()
    service = _service(llm, prompt_center)
    first = _route(service, state)
    second = _route(service, state)
    assert first.selection_summary["cache_hit"] is False
    assert second.selection_summary["cache_hit"] is True
    assert second.selection_summary["latency_ms"] == 0.0
    assert len(llm.calls) == 1
    assert second.decision.turn_scene == first.decision.turn_scene


def test_route_cache_miss_on_new_input(state, prompt_center, monkeypatch):
    monkeypatch.setattr(settings.runtime, "route_cache_enabled", True, raising=False)
    llm = StubRouterLLM()
    service = _service(llm, prompt_center)
    _route(service, state, "解这道方程")
    _route(service, state, "今天天气怎么样")
    assert len(llm.calls) == 2


def test_prepare_turn_with_parallel_prefetch(state, prompt_center, monkeypatch):
    monkeypatch.setattr(settings.runtime, "parallel_prefetch_enabled", True, raising=False)
    llm = StubRouterLLM(delay=0.15)
    service = _service(llm, prompt_center)
    started = time.monotonic()
    prepared = service.prepare_turn(
        prompt_center=prompt_center,
        state=state,
        user_message={"role": "user", "content": text_content("解这道方程")},
        history_window=4,
    )
    elapsed = time.monotonic() - started
    assert prepared.turn_plan.decision.turn_scene == "education"
    assert prepared.turn_plan.payload.input
    # 预取与路由重叠：总耗时应明显小于「路由 + 串行上下文编译」
    assert elapsed < 0.6