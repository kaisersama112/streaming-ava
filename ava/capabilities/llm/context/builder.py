from dataclasses import replace
from typing import Any

from ava.core.context.continuity import (
    build_artifact_brief_for_context,
    select_router_model,
    should_inherit_reference_artifacts,
    should_isolate_current_artifact_context,
)
from ava.core.context.input import build_turn_input
from ava.domain.conversation.state import ConversationState
from ava.domain.multimodal import TurnInput
from configs import settings

from ava.capabilities.llm.context.history import build_visible_history
from ava.capabilities.llm.context.memory import build_memory_projection
from ava.capabilities.llm.context.multimodal import build_multimodal_projection
from ava.capabilities.llm.context.types import InferenceVisibleContext
from ava.capabilities.llm.types import InferenceTask, LLMContext


def _build_visible_context(
    state: ConversationState,
    turn_input: TurnInput,
    *,
    history_window: int,
    current_turn_id: int | None,
    max_context_messages: int,
    profile: str,
    previous_visible_context: InferenceVisibleContext | None = None,
) -> InferenceVisibleContext:
    """构建推理阶段可见的上下文对象。"""

    # 计算最大上下文消息数：
    # - 优先使用 max_context_messages
    # - 否则根据 history_window * 2 推导，因为一轮对话通常包含 user 和 assistant 两条消息
    # - 至少保留 2 条消息
    max_messages = max(2, int(max_context_messages or (history_window * 2)))

    # 如果没有指定当前 turn_id，则直接取最近的 turn records
    if current_turn_id is None:
        turn_records = state.turn_records[-max_messages:]

    # 如果指定了当前 turn_id，则排除当前轮，避免当前输入重复进入历史上下文
    else:
        turn_records = [
            item
            for item in state.turn_records
            if item.get("turn_id") != current_turn_id
        ][-max_messages:]

    # 将 turn records 转换为模型可见的历史消息
    history_messages = build_visible_history(
        turn_records,
        max_messages=max_messages,
    )

    # 当前用户文本：
    # - 优先使用标准化文本
    # - 如果没有文本，则使用多模态摘要兜底
    user_text = turn_input.normalized_text() or turn_input.multimodal_summary()

    # 判断是否应继承上一轮参考附件
    allow_reference_artifacts = should_inherit_reference_artifacts(
        state,
        turn_input,
    )

    # 默认不继承参考附件
    reference_artifacts = ()

    # 仅当允许继承，且当前轮没有新附件时，从最近历史轮次中继承参考附件
    if allow_reference_artifacts and not turn_input.artifacts:
        reference_artifacts = state.recent_reference_artifacts(
            current_turn_id=current_turn_id,
            limit_turns=1,
        )

    # 构建附件简报，用于路由器或响应器快速了解附件上下文
    artifact_brief = build_artifact_brief_for_context(
        state,
        current_artifacts=turn_input.artifacts,
        reference_artifacts=reference_artifacts,
    )

    # 组装推理可见上下文
    visible_context = InferenceVisibleContext(
        turn_input=turn_input,
        user_text=user_text,
        session_id=state.session_id,
        session_scene=state.session_scene,
        turn_scene=state.turn_scene,
        history_messages=history_messages,
        artifacts=turn_input.artifacts,
        reference_artifacts=reference_artifacts,
        turn_records=turn_records,
        context_profile=profile,
        reference_artifacts_inherited=bool(reference_artifacts),
        router_artifact_brief=artifact_brief,
        router_plan={},
    )

    # 如果已有上一阶段构建出的 visible context，则复用其中的路由产物：
    # - router_artifact_brief：路由阶段生成的附件摘要
    # - router_plan：路由阶段生成的计划信息
    #
    # 这样可以避免响应阶段重复计算或丢失路由阶段结论
    if previous_visible_context is not None:
        visible_context = replace(
            visible_context,
            router_artifact_brief=dict(
                getattr(previous_visible_context, "router_artifact_brief", {}) or {}
            ),
            router_plan=dict(
                getattr(previous_visible_context, "router_plan", {}) or {}
            ),
        )

    return visible_context


def build_llm_context(
    *,
    task: InferenceTask,
    state: ConversationState,
    turn_input: TurnInput | str,
    decision=None,
    plan=None,
    history_window: int | None = None,
    max_context_messages: int | None = None,
    current_turn_id: int | None = None,
    visible_context: InferenceVisibleContext | None = None,
) -> LLMContext:
    """根据推理任务类型构建 LLMContext。"""

    # 调用方可以直接传入字符串；这里统一转换为 TurnInput，便于后续处理文本与多模态输入
    if isinstance(turn_input, str):
        turn_input = build_turn_input(turn_input)

    # 历史窗口大小：
    # - 优先使用调用方参数
    # - 否则读取运行时配置
    # - 最后兜底为 8
    history_window = int(
        history_window
        or settings.runtime.history_window
        or 8
    )

    # 路由任务：构建面向 router 的上下文
    if task == InferenceTask.ROUTE:
        # 如果外部已传入 visible_context，则直接复用；
        # 否则构建 router 专用的可见上下文
        base_visible_context = visible_context or _build_visible_context(
            state,
            turn_input,
            history_window=history_window,
            current_turn_id=current_turn_id,
            max_context_messages=int(
                max_context_messages
                or settings.runtime.router_max_context_messages
                or settings.runtime.max_context_messages
                or 8
            ),
            profile="router",
        )

        # 判断当前附件上下文是否应与上一轮隔离
        # 若当前轮上传了不同附件，通常需要清空历史，避免 router 被旧附件上下文干扰
        isolate = should_isolate_current_artifact_context(
            state,
            base_visible_context,
            current_turn_id=current_turn_id,
        )

        # 默认使用原始 router visible context
        route_visible_context = base_visible_context

        # 隔离附件上下文时，将场景重置为通用场景，并清空历史记录
        if isolate:
            route_visible_context = replace(
                base_visible_context,
                session_scene="general",
                turn_scene="general_qa",
                history_messages=[],
                turn_records=[],
            )

        # 读取附件简报，并识别简报来源
        artifact_brief = dict(
            getattr(route_visible_context, "router_artifact_brief", {}) or {}
        )
        artifact_brief_source = str(
            artifact_brief.get("source") or ""
        ).strip()

        # 如果附件简报来自 turn_result 或 llm_brief，说明已有文本化结果；
        # 此时 router 可以走文本模型，避免不必要地调用多模态模型
        text_only_router = artifact_brief_source in {
            "turn_result",
            "llm_brief",
        }

        # 根据是否存在多模态上下文、是否强制文本模式，选择 router 模型
        chosen_model = select_router_model(
            route_visible_context,
            text_only=text_only_router,
            model=str(
                settings.runtime.router_model
                or settings.openai_config.model
                or settings.openai_config.intent_model
            ).strip(),
            multimodal_model=str(
                settings.openai_config.multimodal_model
                or settings.openai_config.model
            ).strip(),
        )

        # 返回路由阶段 LLM 上下文
        return LLMContext(
            task=task,
            session_id=state.session_id,
            current_input=turn_input,
            history=list(route_visible_context.history_messages),
            memory=build_memory_projection(state),
            multimodal=build_multimodal_projection(route_visible_context),
            routing={
                "session_scene": route_visible_context.session_scene,
                "turn_scene": route_visible_context.turn_scene,
                "artifact_brief_source": artifact_brief_source,
                "text_only_router": text_only_router,
                "chosen_model": chosen_model,
                "isolated": isolate,
            },
            metadata={
                # router 实际使用的上下文
                "visible_context": route_visible_context,

                # 未隔离前的原始上下文，便于后续响应阶段或调试使用
                "base_visible_context": base_visible_context,

                # 当前轮 ID，用于排除当前轮历史或追踪上下文构建过程
                "current_turn_id": current_turn_id,
            },
        )

    # 非路由任务：构建面向 responder 或其他推理任务的上下文
    previous_visible_context = (
        visible_context
        if visible_context is not None
        else None
    )

    # 构建响应阶段可见上下文
    responder_visible_context = _build_visible_context(
        state,
        turn_input,
        history_window=history_window,
        current_turn_id=current_turn_id,
        max_context_messages=int(
            max_context_messages
            or settings.runtime.responder_max_context_messages
            or settings.runtime.max_context_messages
            or 16
        ),
        profile="responder_minimal",
        previous_visible_context=previous_visible_context,
    )

    # 返回响应阶段 LLM 上下文
    return LLMContext(
        task=task,
        session_id=state.session_id,
        current_input=turn_input,
        history=list(responder_visible_context.history_messages),
        memory=build_memory_projection(state),
        multimodal=build_multimodal_projection(responder_visible_context),

        # 如果存在执行计划，则将策略信息写入上下文
        strategy=(
            plan.strategy.to_metadata()
            if plan is not None
            else None
        ),

        # 如果存在路由决策，则将其序列化后写入上下文
        routing=(
            decision.model_dump()
            if decision is not None
            else None
        ),

        metadata={
            "visible_context": responder_visible_context,
            "current_turn_id": current_turn_id,
        },
    )

