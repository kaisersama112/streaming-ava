"""多模态引用继承 / 上下文隔离真值表测试。"""

from __future__ import annotations

from ava.domain.multimodal.continuity import (
    artifact_blocks,
    blocks_to_artifacts,
    context_isolation_token,
    should_inherit_visual_context,
)
from tests.conftest import image_content, make_turn, text_content


def _records_with_image():
    return [make_turn(1, image_content("这道题怎么做"), "先移项…")]


def test_new_artifact_is_isolated():
    records = _records_with_image()
    current = {"role": "user", "content": image_content("看这张新图", "data:image/png;base64,BBBB")}
    result = should_inherit_visual_context(current, records)
    assert result.inherit is False
    assert result.reason == "new_artifacts_isolated"


def test_text_followup_inherits_recent_visual():
    records = _records_with_image()
    current = {"role": "user", "content": text_content("第二步为什么这样变形？")}
    result = should_inherit_visual_context(current, records)
    assert result.inherit is True
    assert result.source_turn_id == 1
    assert result.source_blocks


def test_topic_switch_breaks_inheritance():
    records = _records_with_image()
    current = {"role": "user", "content": text_content("换个话题，今天天气怎么样")}
    result = should_inherit_visual_context(current, records)
    assert result.inherit is False


def test_no_visual_history_no_inheritance():
    records = [make_turn(1, text_content("你好"), "你好呀")]
    current = {"role": "user", "content": text_content("继续")}
    assert should_inherit_visual_context(current, records).inherit is False


def test_old_visual_beyond_window_not_inherited():
    records = [
        make_turn(1, image_content("旧题")),
        make_turn(2, text_content("谢谢"), "不客气"),
        make_turn(3, text_content("再见"), "再见"),
        make_turn(4, text_content("嗯"), "嗯"),
    ]
    current = {"role": "user", "content": text_content("再讲一遍")}
    result = should_inherit_visual_context(current, records, max_turns=2)
    assert result.inherit is False


def test_isolation_token_differs_per_artifact():
    a = {"role": "user", "content": image_content("a", "data:image/png;base64,AAAA")}
    b = {"role": "user", "content": image_content("b", "data:image/png;base64,BBBB")}
    assert context_isolation_token(a) != context_isolation_token(b)
    assert context_isolation_token(a) == context_isolation_token(dict(a))


def test_blocks_to_artifacts_shape():
    message = {"role": "user", "content": image_content("题目")}
    artifacts = blocks_to_artifacts(artifact_blocks(message))
    assert artifacts and artifacts[0]["kind"] == "image"
    assert artifacts[0]["data_url"].startswith("data:image")
    assert "reference_token" in artifacts[0]["metadata"]