"""User-facing command handlers shared by CLI and debugging flows."""

from ava.pipeline.agent.sessions import clear_agent_session
from ava.domain.conversation.state import ConversationState


def handle_state_command(text: str, state: ConversationState) -> bool:
    if text.startswith("/fact "):
        raw = text[len("/fact ") :].strip()
        if "=" not in raw:
            print("用法: /fact key=value")
            return True
        key, value = raw.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or not value:
            print("用法: /fact key=value")
            return True
        state.memory.facts[key] = value
        state.save()
        print(f"[fact] 已设置 {key}={value}")
        return True

    if text == "/facts":
        if not state.memory.facts:
            print("[fact] 当前为空")
            return True
        print("[fact] 当前事实槽")
        for k, v in sorted(state.memory.facts.items()):
            print(f"- {k}={v}")
        return True

    if text == "/memory":
        print(f"[memory] 轮次={state.turn_count}")
        print(f"[memory] intent统计={state.intent_counter}")
        print(f"[memory] 最近话题={list(state.memory.recent_topics)}")
        print(f"[memory] session_scene={state.session_scene}, turn_scene={state.turn_scene}")
        print(f"[memory] education_state={state.memory.education_state}")
        print(f"[memory] context_summary={state.memory.context_summary}")
        print(f"[memory] multimodal_context_summary={state.memory.multimodal_context_summary}")
        print(f"[memory] multimodal_turns={len(state.turn_records)}")
        return True

    if text == "/reset":
        state.reset()
        clear_agent_session(state.session_id)
        print("[memory] 已重置")
        return True

    return False
