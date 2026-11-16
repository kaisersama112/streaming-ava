"""链路优化：动态选模 / Responses 续接 / 兜底降级 / 编排路径。"""

from __future__ import annotations

import pytest

from ava.inference_runtime.service import ReplyService
from ava.inference_runtime.types import (
    TurnPlan,
    TurnPlanDebug,
    TurnPlanExecution,
    TurnPlanPayload,
    TurnPlanRuntimeContext,
)
from ava.intent.orchestrator import SkillOrchestrator
from ava.llm_model_executor.types import InferenceCompleted, InferenceResult, OutputTextDelta
from ava.multi_turn_context_builder import ContextCompiler, ConversationBuildOptions
from ava.router_selector.schema import RouteDecision
from configs import settings
from tests.conftest import image_content, text_content
from tests.test_orchestrator import StubRunner


class StubLLM:
    def __init__(self, *, fail_models: set[str] | None = None):
        self.fail_models = fail_models or set()
        self.requests = []

    def generate(self, context):
        self.requests.append(context)
        if context.model in self.fail_models:
            raise RuntimeError(f"{context.model} unavailable")
        return InferenceResult(text=f"reply-from-{context.model}", metadata={"response_id": "resp_new"})

    def stream_generate(self, context, *, stop_event=None):
        self.requests.append(context)
        if context.model in self.fail_models:
            raise RuntimeError(f"{context.model} unavailable")
        yield OutputTextDelta("你好")
        yield OutputTextDelta("世界")
        yield InferenceCompleted(text="你好世界", metadata={"response_id": "resp_stream"})


def _plan(state, user_message, *, turn_scene="general_qa", confidence=0.9, router_plan=None):
    context = ContextCompiler().build_conversation_context(
        state=state,
        user_message=user_message,
        options=ConversationBuildOptions(history_window=4, max_context_messages=8, profile="responder"),
    )
    decision = RouteDecision(
        session_scene="education" if turn_scene == "education" else "general",
        turn_scene=turn_scene,
        intent="solve" if turn_scene == "education" else "qa",
        confidence=confidence,
        should_preserve_teaching_state=turn_scene == "education",
    )
    return TurnPlan(
        decision=decision,
        strategy=None,
        prompt_package=None,
        payload=TurnPlanPayload(instructions="系统指令", input=[dict(user_message)]),
        execution=TurnPlanExecution(orchestrator_name="test", model=""),
        runtime_context=TurnPlanRuntimeContext(conversation_context=context),
        debug=TurnPlanDebug(router_plan=dict(router_plan or {})),
    )


@pytest.fixture(autouse=True)
def _runtime_flags(monkeypatch):
    monkeypatch.setattr(settings.runtime, "model_selection_enabled", True, raising=False)
    monkeypatch.setattr(settings.runtime, "small_model", "edge-3b", raising=False)
    monkeypatch.setattr(settings.runtime, "fallback_model", "cloud-fallback", raising=False)
    monkeypatch.setattr(settings.runtime, "model_selection_min_confidence", 0.75, raising=False)
    monkeypatch.setattr(settings.runtime, "responder_continuity_enabled", False, raising=False)
    monkeypatch.setattr(settings.runtime, "multi_intent_enabled", False, raising=False)
    monkeypatch.setattr(settings.runtime, "agents_sdk_enabled", False, raising=False)
    monkeypatch.setattr(settings.runtime, "trace_enabled", False, raising=False)


def test_simple_high_confidence_uses_small_model(state):
    llm = StubLLM()
    service = ReplyService(llm_service=llm)
    message = {"role": "user", "content": text_content("今天星期几")}
    plan = _plan(state, message)
    result = service.generate(state=state, session_id=state.session_id, plan=plan, model="cloud-large", user_message=message)
    assert llm.requests[0].model == "edge-3b"
    assert result.debug["model_selection"]["tier"] == "small"


def test_education_uses_large_model(state):
    llm = StubLLM()
    service = ReplyService(llm_service=llm)
    message = {"role": "user", "content": text_content("解这道方程")}
    plan = _plan(state, message, turn_scene="education")
    service.generate(state=state, session_id=state.session_id, plan=plan, model="cloud-large", user_message=message)
    assert llm.requests[0].model == "cloud-large"


def test_low_confidence_uses_large_model(state):
    llm = StubLLM()
    service = ReplyService(llm_service=llm)
    message = {"role": "user", "content": text_content("嗯")}
    plan = _plan(state, message, confidence=0.4)
    service.generate(state=state, session_id=state.session_id, plan=plan, model="cloud-large", user_message=message)
    assert llm.requests[0].model == "cloud-large"


def test_multimodal_uses_large_model(state):
    llm = StubLLM()
    service = ReplyService(llm_service=llm)
    message = {"role": "user", "content": image_content("这题")}
    plan = _plan(state, message)
    service.generate(state=state, session_id=state.session_id, plan=plan, model="cloud-large", user_message=message)
    assert llm.requests[0].model == "cloud-large"


def test_fallback_model_on_primary_failure(state):
    llm = StubLLM(fail_models={"cloud-large"})
    service = ReplyService(llm_service=llm)
    message = {"role": "user", "content": text_content("讲一下勾股定理")}
    plan = _plan(state, message, turn_scene="education")
    result = service.generate(state=state, session_id=state.session_id, plan=plan, model="cloud-large", user_message=message)
    assert [request.model for request in llm.requests] == ["cloud-large", "cloud-fallback"]
    assert result.debug["model_selection"]["tier"] == "fallback"
    assert "cloud-fallback" in result.assistant_message["content"][0]["text"]


def test_continuity_sends_previous_response_id_and_trims_history(state, monkeypatch):
    monkeypatch.setattr(settings.runtime, "responder_continuity_enabled", True, raising=False)
    state.update_responder_conversation_state(previous_response_id="resp_prev", conversation_id="conv_1")
    llm = StubLLM()
    service = ReplyService(llm_service=llm)
    message = {"role": "user", "content": text_content("继续")}
    plan = _plan(state, message)
    plan.payload.input.insert(0, {"role": "assistant", "content": [{"type": "output_text", "text": "历史"}]})
    result = service.generate(state=state, session_id=state.session_id, plan=plan, model="cloud-large", user_message=message)
    request = llm.requests[0]
    assert request.metadata["previous_response_id"] == "resp_prev"
    assert request.metadata["conversation_id"] == "conv_1"
    assert state.responder_previous_response_id == "resp_new"
    assert result.debug["response_metadata"]["response_id"] == "resp_new"


def test_continuity_disabled_for_new_artifact(state, monkeypatch):
    monkeypatch.setattr(settings.runtime, "responder_continuity_enabled", True, raising=False)
    state.update_responder_conversation_state(previous_response_id="resp_prev")
    llm = StubLLM()
    service = ReplyService(llm_service=llm)
    message = {"role": "user", "content": image_content("新图", "data:image/png;base64,ZZZZ")}
    plan = _plan(state, message)
    service.generate(state=state, session_id=state.session_id, plan=plan, model="cloud-large", user_message=message)
    assert "previous_response_id" not in llm.requests[0].metadata
    # 新附件切断旧链路，但本轮回复建立新的续接链
    assert state.responder_previous_response_id == "resp_new"


def test_stream_captures_response_id_and_first_token(state):
    llm = StubLLM()
    service = ReplyService(llm_service=llm)
    tokens = []
    message = {"role": "user", "content": text_content("你好")}
    plan = _plan(state, message)
    result = service.stream(
        state=state,
        session_id=state.session_id,
        plan=plan,
        model="cloud-large",
        on_token=tokens.append,
        user_message=message,
    )
    assert tokens == ["你好", "世界"]
    assert result.debug["response_metadata"]["response_id"] == "resp_stream"
    assert result.debug["first_token_ms"] is not None


def test_orchestration_path_merges_and_applies_whitelist_patches(state, monkeypatch):
    monkeypatch.setattr(settings.runtime, "multi_intent_enabled", True, raising=False)
    monkeypatch.setattr(settings.runtime, "agents_sdk_orchestration_mode", "serial", raising=False)
    orchestrator = SkillOrchestrator(runner=StubRunner())
    service = ReplyService(llm_service=StubLLM(), orchestrator=orchestrator)
    message = {"role": "user", "content": text_content("批改并评估这道题")}
    plan = _plan(
        state,
        message,
        turn_scene="education",
        router_plan={"module": "check", "secondary_actions": ["assess"]},
    )
    tokens = []
    result = service.stream(
        state=state,
        session_id=state.session_id,
        plan=plan,
        model="cloud-large",
        on_token=tokens.append,
        user_message=message,
        context=plan.runtime_context.conversation_context,
    )
    assert result.backend == "skill_orchestrator"
    assert "[check] 结果" in result.assistant_message["content"][0]["text"]
    assert "[assess] 结果" in result.assistant_message["content"][0]["text"]
    assert tokens
    applied = result.debug["applied_state_patches"]
    kp_patches = [item for item in applied if item["key"] == "knowledge_point"]
    assert [item["value"] for item in kp_patches] == ["check-kp", "assess-kp"]
    # 串行编排按序应用，后写的 assess 覆盖 check
    assert state.memory.education_state.get("knowledge_point") == "assess-kp"


def test_orchestration_rejects_non_whitelist_patches(state, monkeypatch):
    monkeypatch.setattr(settings.runtime, "multi_intent_enabled", True, raising=False)

    class EvilRunner(StubRunner):
        def __call__(self, task, ctx, *, stop_event=None):
            from ava.intent.types import SubAgentResult

            return SubAgentResult(
                task_id=task.task_id,
                skill=task.skill,
                status="ok",
                text="ok",
                patches=[{"key": "session_id", "value": "hijack"}, {"key": "level", "value": "fluent"}],
            )

    service = ReplyService(llm_service=StubLLM(), orchestrator=SkillOrchestrator(runner=EvilRunner()))
    message = {"role": "user", "content": text_content("解题")}
    plan = _plan(state, message, turn_scene="education", router_plan={"module": "solve"})
    result = service.generate(
        state=state,
        session_id=state.session_id,
        plan=plan,
        model="cloud-large",
        user_message=message,
        context=plan.runtime_context.conversation_context,
    )
    assert state.session_id == "test-session"
    assert state.memory.education_state.get("level") == "fluent"
    assert result.debug["rejected_state_patches"]