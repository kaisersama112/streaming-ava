"""路由置信度策略。

这里刻意把策略层与响应解析层分开：
先让模型给出原始决策，再由策略层把结果归一化为更安全的最终路由。
"""

from __future__ import annotations

from .schema import RouteDecision


class RouterDecisionPolicy:
    """把原始 router 决策归一化为更稳妥的最终决策。"""

    def _clarify_decision(self, current_session_scene: str) -> RouteDecision:
        return RouteDecision(
            session_scene="education" if current_session_scene == "education" else "general",
            turn_scene="clarify",
            intent="clarify",
            confidence=0.49,
            should_preserve_teaching_state=(current_session_scene == "education"),
            need_clarification=True,
        )

    def apply(
        self,
        decision: RouteDecision,
        *,
        current_session_scene: str,
    ) -> RouteDecision:
        if decision.turn_scene == "education":
            decision.session_scene = "education"
            decision.should_preserve_teaching_state = True
        if decision.turn_scene == "clarify":
            decision.need_clarification = True

        if decision.confidence < 0.5:
            return self._clarify_decision(current_session_scene)

        if decision.confidence < 0.8:
            if current_session_scene == "education" and decision.turn_scene in {"general_qa", "casual_chat"}:
                decision.session_scene = "education"
                decision.should_preserve_teaching_state = True
                return decision
            if current_session_scene != decision.session_scene:
                return self._clarify_decision(current_session_scene)

        return decision
