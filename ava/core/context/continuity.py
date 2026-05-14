"""用于快照组装与路由隔离的共享连续性启发式规则。"""

from __future__ import annotations

from ava.domain.conversation import ContextSnapshot
from ava.domain.multimodal import TurnInput
from ava.domain.conversation.state import ConversationState


def should_inherit_reference_artifacts(
    state: ConversationState,
    turn_input: TurnInput,
) -> bool:
    """判断当前轮次是否应该继承上一轮的参考附件。"""

    # 当前输入已经带有新附件时，不再继承历史附件，避免新旧附件混淆
    if turn_input.artifacts:
        return False

    # 获取当前输入文本；没有文本时无法判断指代关系，因此不继承
    text = (turn_input.normalized_text() or "").strip().lower()
    if not text:
        return False

    # 读取教育场景中的上一轮策略、政策和学习场景信息，用于判断短文本是否承接上一轮上下文
    previous_strategy_id = str(
        state.memory.education_state.get("previous_strategy_id") or ""
    ).strip()
    previous_policy_id = str(
        state.memory.education_state.get("previous_policy_id") or ""
    ).strip()
    learning_scenario = str(
        state.memory.education_state.get("learning_scenario") or ""
    ).strip()

    # 如果上一轮存在策略 ID，且当前文本很短，通常表示“继续”“这个呢”等承接式追问
    if previous_strategy_id and len(text) <= 12:
        return True

    # 如果处于 lesson 场景，或上一轮 policy 属于 lesson 系列，
    # 则稍微放宽短文本长度阈值，以支持教学过程中的连续追问
    if (learning_scenario == "lesson" or previous_policy_id.startswith("lesson.")) and len(text) <= 24:
        return True

    # 默认不继承参考附件，避免错误携带历史多模态上下文
    return False


def build_artifact_brief_for_context(
    state: ConversationState,
    *,
    current_artifacts,
    reference_artifacts,
) -> dict[str, object]:
    """为当前上下文构建附件摘要信息。"""

    # 优先使用当前轮次附件；如果当前轮次没有附件，则使用继承得到的参考附件
    target_artifacts = current_artifacts or reference_artifacts

    # 没有任何附件时，不生成 artifact brief
    if not target_artifacts:
        return {}

    # 从缓存或 metadata 中读取附件分析结果，避免重复进行多模态分析
    return state.memory.cached_or_metadata_artifact_analysis(target_artifacts)


def should_isolate_current_artifact_context(
    state: ConversationState,
    snapshot: ContextSnapshot,
    *,
    current_turn_id: int | None = None,
) -> bool:
    """判断当前附件上下文是否应与上一轮附件上下文隔离。"""

    # 当前轮次没有附件时，不需要隔离附件上下文
    current_artifacts = tuple(snapshot.artifacts or ())
    if not current_artifacts:
        return False

    # 获取上一轮可继承的参考附件
    previous_artifacts = state.recent_reference_artifacts(
        current_turn_id=current_turn_id,
        limit_turns=1,
    )

    # 如果当前有附件，而上一轮没有附件，则当前附件自然形成新的上下文
    if not previous_artifacts:
        return True

    # 分别计算当前附件组和上一轮附件组的稳定 key，用于判断是否是同一批附件
    current_key = state.memory.artifact_bundle_key(current_artifacts)
    previous_key = state.memory.artifact_bundle_key(previous_artifacts)

    # 如果 key 存在且相同，说明当前附件与上一轮附件一致，无需隔离
    if current_key and current_key == previous_key:
        return False

    # 当前附件与上一轮附件不同，应该隔离，防止路由器误用旧附件上下文
    return True


def select_router_model(
    snapshot: ContextSnapshot,
    *,
    text_only: bool,
    model: str,
    multimodal_model: str,
) -> str:
    """根据当前上下文选择路由模型。"""

    # 如果显式要求文本模式，则始终使用文本模型
    if text_only:
        return model

    # 当前轮次存在附件，或继承了参考附件时，需要使用多模态模型
    if snapshot.artifacts or snapshot.reference_artifacts:
        return multimodal_model

    # 默认使用文本模型
    return model