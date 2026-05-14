from typing import Any

from ava.domain.conversation.strategy import BranchStrategy
from ava.capabilities.llm.context.types import InferenceVisibleContext


def build_multimodal_projection(
    visible_context: InferenceVisibleContext,
) -> dict[str, Any]:
    """从可见上下文中提取模型可见的多模态投影信息。"""

    return {
        # 当前轮次直接携带的附件数量
        "artifacts_count": len(visible_context.artifacts),

        # 从历史上下文继承来的参考附件数量
        "reference_artifacts_count": len(visible_context.reference_artifacts),

        # 是否发生了参考附件继承
        "reference_artifacts_inherited": bool(
            visible_context.reference_artifacts_inherited
        ),

        # 路由阶段生成或继承的附件简报，用于辅助后续策略判断
        "router_artifact_brief": dict(
            visible_context.router_artifact_brief or {}
        ),
    }


def should_attach_reference_artifacts(
    visible_context: InferenceVisibleContext,
    strategy: BranchStrategy | None,
) -> bool:
    """判断响应阶段是否需要重新附加参考附件。"""

    # 以下情况不附加参考附件：
    # - 当前轮次已有新附件，避免新旧附件混用
    # - 没有可继承的参考附件
    # - 没有策略对象，无法判断是否需要视觉重读
    if (
        visible_context.artifacts
        or not visible_context.reference_artifacts
        or strategy is None
    ):
        return False

    # 读取路由阶段的附件简报
    artifact_brief = dict(
        getattr(visible_context, "router_artifact_brief", {}) or {}
    )

    # 如果已有附件简报，则优先信任简报中的显式判断：
    # - followup_requires_visual_reread=True：需要重新附加附件进行视觉读取
    # - 否则：认为文本化简报已足够，不再附加原始附件
    if artifact_brief:
        if bool(artifact_brief.get("followup_requires_visual_reread", False)):
            return True
        return False

    # 没有 artifact brief 时，从策略分析结构中读取连续性判断
    analysis = dict(getattr(strategy, "analysis", {}) or {})

    # continuity 通常描述当前轮是否需要承接上一轮上下文
    continuity = dict(analysis.get("continuity", {}) or {})

    # education_turn_frame 通常描述教育场景下的轮次结构、策略边界和学习对象
    education_turn_frame = dict(
        analysis.get("education_turn_frame", {}) or {}
    )

    # 场景策略信息，例如 answer_boundary 等
    scenario_policy = dict(
        education_turn_frame.get("scenario_policy", {}) or {}
    )

    # 学习对象集合；清理空白并过滤空值，便于后续 membership 判断
    learning_objects = {
        str(item).strip()
        for item in (education_turn_frame.get("learning_objects") or [])
        if str(item).strip()
    }

    # 满足任一条件则附加参考附件：
    # - continuity 明确要求携带参考附件
    # - 答案边界为 contextual_only，说明回答必须依赖上下文
    # - 学习对象包含 lesson_segment，说明当前轮仍处于课段上下文中
    return bool(
        continuity.get("carry_reference_artifacts")
        or scenario_policy.get("answer_boundary") == "contextual_only"
        or "lesson_segment" in learning_objects
    )


def artifacts_to_blocks(artifacts) -> list[dict[str, Any]]:
    """将附件对象转换为可发送给模型的消息 block 列表。"""

    blocks: list[dict[str, Any]] = []

    # 遍历附件集合；artifacts 可能为 None，因此先用空列表兜底
    for artifact in list(artifacts or []):
        # 每个 artifact 自己负责转换为模型消息 block
        block = artifact.to_message_block()

        # 过滤掉空 block，避免向模型发送无效内容
        if block:
            blocks.append(block)

    return blocks