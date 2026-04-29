"""User-facing command handlers shared by CLI and debugging flows."""

from ava.domain.session.state import ConversationState


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
        state.facts[key] = value
        state.save()
        print(f"[fact] 已设置 {key}={value}")
        return True

    if text == "/facts":
        if not state.facts:
            print("[fact] 当前为空")
            return True
        print("[fact] 当前事实槽:")
        for k, v in sorted(state.facts.items()):
            print(f"- {k}={v}")
        return True

    if text == "/memory":
        print(f"[memory] 轮次={state.turn_count}")
        print(f"[memory] intent统计={state.intent_counter}")
        print(f"[memory] 最近话题={list(state.recent_topics)}")
        print(f"[memory] session_scene={state.session_scene}, turn_scene={state.turn_scene}")
        print(f"[memory] education_state={state.education_state}")
        print(f"[memory] context_summary={state.context_summary}")
        print(f"[memory] multimodal_context_summary={state.multimodal_context_summary}")
        print(f"[memory] multimodal_turns={len(state.turn_records)}")
        return True

    if text == "/reset":
        state.reset()
        print("[memory] 已重置")
        return True

    return False
