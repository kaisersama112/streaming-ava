"""Context Compiler 分层编译 / 运行时注入 / 历史裁剪测试。"""

from __future__ import annotations

from ava.multi_turn_context_builder import ContextCompiler, ConversationBuildOptions
from ava.multi_turn_context_builder.compiler import context_snapshot_hash
from ava.router_selector.schema import RouteDecision
from ava.router_selector.strategy_builder import build_strategy_from_model_plan
from tests.conftest import image_content, make_turn, text_content


def _context(state, user_message, profile="router", current_turn_id=None):
    return ContextCompiler().build_conversation_context(
        state=state,
        user_message=user_message,
        options=ConversationBuildOptions(
            history_window=4,
            current_turn_id=current_turn_id,
            max_context_messages=8,
            profile=profile,
        ),
    )


def test_router_payload_layers(state, prompt_center):
    state.turn_records.append(make_turn(1, text_content("你好"), "你好"))
    message = {"role": "user", "content": text_content("勾股定理是什么")}
    context = _context(state, message)
    payload = ContextCompiler().compile_router_payload(
        prompt_center=prompt_center, context=context, state=state
    )
    assert set(payload.layers) == {"system", "developer", "history", "user"}
    assert payload.layers["system"]
    assert "运行时状态" in payload.layers["developer"]
    assert payload.instructions.startswith(payload.layers["system"])
    assert payload.input[-1] == payload.layers["user"]
    assert payload.sections.get("runtime")


def test_responder_payload_injects_runtime_and_skills(state, prompt_center):
    state.memory.set_education_state_value("subject", "math")
    state.memory.set_user_fact("grade", "初二")
    message = {"role": "user", "content": text_content("讲一下勾股定理")}
    context = _context(state, message, profile="responder")
    decision = RouteDecision(
        session_scene="education",
        turn_scene="education",
        intent="explain",
        confidence=0.9,
        should_preserve_teaching_state=True,
    )
    strategy = build_strategy_from_model_plan(
        prompt_center,
        decision,
        context,
        router_plan={"module": "explain", "subject": "math", "pedagogy": "step-by-step"},
    )
    payload = ContextCompiler().compile_responder_payload(
        prompt_center=prompt_center,
        context=context,
        strategy=strategy,
        decision=decision,
        state=state,
    )
    assert payload.active_skills
    assert "初二" in payload.layers["developer"]
    assert payload.layers["history"] == []
    assert payload.input[-1]["role"] == "user"


def test_history_artifacts_trimmed_for_router(state, prompt_center):
    state.turn_records.append(make_turn(1, image_content("这道题"), "移项"))
    message = {"role": "user", "content": text_content("第二步呢")}
    context = _context(state, message)
    payload = ContextCompiler().compile_router_payload(
        prompt_center=prompt_center, context=context, state=state
    )
    history_blocks = [
        block
        for item in payload.layers["history"]
        for block in item.get("content", [])
        if isinstance(block, dict)
    ]
    assert all(
        block.get("type") not in {"input_image", "input_audio", "input_file"}
        for block in history_blocks
    )
    assert any("历史图片" in str(block.get("text", "")) for block in history_blocks)
    # 当前轮原始多模态块保留
    current = {"role": "user", "content": image_content("新题", "data:image/png;base64,CCCC")}
    context2 = _context(state, current)
    payload2 = ContextCompiler().compile_router_payload(
        prompt_center=prompt_center, context=context2, state=state
    )
    assert any(
        block.get("type") == "input_image"
        for block in payload2.layers["user"]["content"]
    )


def test_visual_followup_runtime_payload(state, prompt_center):
    state.turn_records.append(make_turn(1, image_content("解这道方程"), "先移项"))
    state.memory.refresh_summaries(turn_records=state.turn_records)
    message = {"role": "user", "content": text_content("为什么第二步要除以2")}
    context = _context(state, message, profile="responder")
    decision = RouteDecision(
        session_scene="education",
        turn_scene="education",
        intent="explain",
        confidence=0.85,
        should_preserve_teaching_state=True,
    )
    strategy = build_strategy_from_model_plan(
        prompt_center, decision, context, router_plan={"module": "explain", "subject": "math"}
    )
    payload = ContextCompiler().compile_responder_payload(
        prompt_center=prompt_center,
        context=context,
        strategy=strategy,
        decision=decision,
        state=state,
    )
    developer = payload.layers["developer"]
    assert '"inherit":true' in developer
    assert '"source_turn_id":1' in developer
    assert state.memory.message_block_analysis_cache


def test_new_artifact_isolated_in_runtime(state, prompt_center):
    state.turn_records.append(make_turn(1, image_content("旧题", "data:image/png;base64,AAAA"), "旧答案"))
    message = {"role": "user", "content": image_content("新题", "data:image/png;base64,BBBB")}
    context = _context(state, message, profile="responder")
    decision = RouteDecision(
        session_scene="education",
        turn_scene="education",
        intent="solve",
        confidence=0.9,
        should_preserve_teaching_state=True,
    )
    strategy = build_strategy_from_model_plan(
        prompt_center, decision, context, router_plan={"module": "solve", "subject": "math"}
    )
    payload = ContextCompiler().compile_responder_payload(
        prompt_center=prompt_center,
        context=context,
        strategy=strategy,
        decision=decision,
        state=state,
    )
    assert '"inherit":false' in payload.layers["developer"]
    assert "new_artifacts_isolated" in payload.layers["developer"]


def test_snapshot_hash_stable(state, prompt_center):
    message = {"role": "user", "content": text_content("你好")}
    context = _context(state, message)
    compiler = ContextCompiler()
    a = compiler.compile_router_payload(prompt_center=prompt_center, context=context, state=state)
    b = compiler.compile_router_payload(prompt_center=prompt_center, context=context, state=state)
    assert context_snapshot_hash(a.instructions, a.input) == context_snapshot_hash(b.instructions, b.input)