"""推理运行时核心类型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ava.domain.conversation.strategy import BranchStrategy
    from ava.llm_model_executor.types import ModelRequestContext
    from ava.multi_turn_context_builder.types import ConversationContext
    from ava.router_selector.schema import RouteDecision


@dataclass(frozen=True)
class TurnPlanPayload:
    """当前轮最终发给模型执行器的正式请求载荷。

    字段说明：
    - `instructions`：
      当前轮系统指令文本。
      这部分由 `multi_turn_context_builder` 结合 prompt 资产、路由决策和策略对象编译得到，
      会作为模型请求中的顶层 `instructions` 传入。
    - `input`：
      当前轮模型输入消息数组。
      这是标准多轮消息数组，按对话顺序排列，通常包含：
      1. 可见历史消息
      2. 当前轮 `user_message`

      这里的每个元素都应当是标准消息对象，例如：
      - `{"role": "user", "content": [...]}`
      - `{"role": "assistant", "content": [...]}`
    """

    instructions: str
    input: list[dict[str, object]]


@dataclass(frozen=True)
class TurnPlanDebug:
    """当前轮计划的调试与可观测信息。

    这些字段不直接参与模型执行，
    主要用于：
    - 调试面板展示
    - 事件日志输出
    - 回放 / 诊断当前轮计划来源

    字段说明：
    - `router_plan`：
      路由模型输出中的原始 `plan` 字段。
      这是“路由层的中间规划结果”，供策略构造与问题排查使用。
    - `prompt_sections`：
      prompt 编译阶段拆出来的命名片段。
      例如 router / responder 阶段的主要文本块，可用于调试查看。
    - `active_skills`：
      prompt 编译过程中判定为激活的技能列表。
      当前实现里通常为空列表，但保留为正式结构，方便后续扩展。
    """

    router_plan: dict[str, Any] = field(default_factory=dict)
    prompt_sections: dict[str, Any] = field(default_factory=dict)
    active_skills: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TurnPlanRuntimeContext:
    """当前轮执行时需要携带的运行时上下文。

    这部分数据不会直接原样传给模型，
    而是给运行时、Agent 后端、TTS、调试和落盘逻辑使用。

    字段说明：
    - `conversation_context`：
      当前轮可见的正式多轮上下文对象。
      运行时、Agent 后端以及调试事件会依赖它。
    """

    conversation_context: "ConversationContext"


@dataclass(frozen=True)
class TurnPlanExecution:
    """当前轮执行控制信息。

    字段说明：
    - `orchestrator_name`：
      当前轮计划由哪个编排器生成。
      用于调试、事件上报和可观测性展示。
    - `model`：
      当前轮回复阶段希望优先使用的模型名。
      若为空，则由执行层按运行时默认配置回退。
    """

    orchestrator_name: str
    model: str = ""


@dataclass(frozen=True)
class TurnPlan:
    """当前轮执行计划。

    `TurnPlan` 是四层正式架构中，
    从 `router_selector` 交给 `inference_runtime` 的唯一正式执行对象。

    可以把它理解为：
    - `decision`：这一轮被路由成什么
    - `strategy`：这一轮应该按什么策略回答
    - `payload`：这一轮真正送给模型的请求载荷
    - `execution`：这一轮执行时使用的编排与模型控制信息
    - `runtime_context`：这一轮运行时附带的上下文对象
    - `debug`：这一轮用于调试和追踪的补充信息

    设计边界：
    - `TurnPlan` 不负责“怎么推导出来”
    - `TurnPlan` 只表达“当前轮最终该怎么执行”
    - `inference_runtime` 只消费 `TurnPlan`
    """

    decision: "RouteDecision"
    strategy: "BranchStrategy | None"
    payload: TurnPlanPayload
    execution: TurnPlanExecution
    runtime_context: TurnPlanRuntimeContext
    debug: TurnPlanDebug = field(default_factory=TurnPlanDebug)

    @property
    def orchestrator_name(self) -> str:
        """兼容访问：返回当前轮编排器名称。"""
        return self.execution.orchestrator_name

    @property
    def instructions(self) -> str:
        """兼容访问：返回当前轮系统指令文本。"""
        return self.payload.instructions

    @property
    def input(self) -> list[dict[str, object]]:
        """兼容访问：返回当前轮模型输入消息数组。"""
        return self.payload.input

    @property
    def model(self) -> str:
        """兼容访问：返回当前轮优先模型名。"""
        return self.execution.model

    @property
    def router_plan(self) -> dict[str, Any]:
        """兼容访问：返回路由阶段原始 plan。"""
        return self.debug.router_plan

    @property
    def metadata(self) -> dict[str, Any]:
        """兼容访问：返回历史代码仍会读取的元信息字典。

        当前仅用于过渡期读取；
        正式代码应优先访问：
        - `runtime_context`
        - `debug`
        - `payload`
        - `execution`
        """
        return {
            "context": self.runtime_context.conversation_context,
            "sections": dict(self.debug.prompt_sections),
            "active_skills": list(self.debug.active_skills),
        }
