"""离线测试夹具：不依赖任何外部 API / 模型权重。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Windows 注册表 ProxyOverride 含 "[::1]" 时，urllib/httpx 会解析出非法端口，
# 导致 fastrtc 等库在 import 期创建 httpx client 直接崩溃。
os.environ.setdefault("NO_PROXY", "localhost,127.0.0.1")
os.environ.setdefault("no_proxy", "localhost,127.0.0.1")

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import pytest

from ava.capabilities.prompt.factories import build_prompt_center
from ava.domain.conversation.state import ConversationState


@pytest.fixture()
def prompt_center():
    return build_prompt_center()


@pytest.fixture()
def state(tmp_path):
    return ConversationState(state_file=tmp_path / "state.json", session_id="test-session")


def make_turn(turn_id: int, user_content, assistant_text: str = "好的", status: str = "completed") -> dict:
    return {
        "turn_id": turn_id,
        "user_message": {"role": "user", "content": user_content},
        "assistant_message": {
            "role": "assistant",
            "content": [{"type": "output_text", "text": assistant_text}],
        },
        "turn_status": status,
    }


def text_content(text: str) -> list[dict]:
    return [{"type": "input_text", "text": text}]


def image_content(text: str, url: str = "data:image/png;base64,AAAA") -> list[dict]:
    return [
        {"type": "input_text", "text": text},
        {"type": "input_image", "image_url": url},
    ]