"""Fallback router used when the LLM router is unavailable or invalid."""

from __future__ import annotations

from ava.domain.context import TurnInput
from ava.domain.routing import RouteDecision


def heuristic_route(user_input: TurnInput | str, session_scene: str) -> RouteDecision:
    if isinstance(user_input, TurnInput):
        t = user_input.normalized_text().strip().lower()
        has_media = bool(user_input.artifacts)
    else:
        t = user_input.strip().lower()
        has_media = False

    edu_keywords = [
        "讲解",
        "题",
        "作业",
        "学习",
        "老师",
        "知识点",
        "辅导",
        "步骤",
        "数学",
        "英语",
        "语文",
        "物理",
        "历史",
        "计算",
        "怎么做",
        "咋做",
        "选哪个",
        "积分",
        "导数",
        "方程",
        "证明",
        "曲线积分",
    ]
    edu_followup_keywords = ["不会", "不会做", "没懂", "不懂", "看不懂", "听不懂", "卡住", "下一步", "继续", "然后呢"]
    general_keywords = ["天气", "新闻", "汇率", "价格", "时间", "谁是", "多少", "在哪"]
    chat_keywords = ["你好", "哈哈", "在吗", "晚安", "早上好", "聊聊"]

    if has_media and not t:
        return RouteDecision(
            session_scene=("education" if session_scene == "education" else "general"),
            turn_scene="clarify",
            intent="clarify",
            confidence=0.55,
            should_preserve_teaching_state=True,
            need_clarification=True,
        )

    if not t or len(t) <= 1:
        return RouteDecision(
            session_scene=("education" if session_scene == "education" else "general"),
            turn_scene="clarify",
            intent="clarify",
            confidence=0.3,
            should_preserve_teaching_state=True,
            need_clarification=True,
        )

    if any(k in t for k in edu_keywords):
        return RouteDecision(
            session_scene="education",
            turn_scene="education",
            intent="education",
            confidence=0.82,
            should_preserve_teaching_state=True,
            need_clarification=False,
        )

    if session_scene == "education" and len(t) <= 18 and any(k in t for k in edu_followup_keywords):
        return RouteDecision(
            session_scene="education",
            turn_scene="education",
            intent="solve_problem",
            confidence=0.86,
            should_preserve_teaching_state=True,
            need_clarification=False,
        )

    if any(k in t for k in general_keywords):
        return RouteDecision(
            session_scene=("education" if session_scene == "education" else "general"),
            turn_scene="general_qa",
            intent="general_qa",
            confidence=0.82,
            should_preserve_teaching_state=(session_scene == "education"),
            need_clarification=False,
        )

    if any(k in t for k in chat_keywords):
        return RouteDecision(
            session_scene=("education" if session_scene == "education" else "general"),
            turn_scene="casual_chat",
            intent="casual_chat",
            confidence=0.82,
            should_preserve_teaching_state=(session_scene == "education"),
            need_clarification=False,
        )

    return RouteDecision(
        session_scene=("education" if session_scene == "education" else "general"),
        turn_scene="clarify",
        intent="clarify",
        confidence=0.45,
        should_preserve_teaching_state=True,
        need_clarification=True,
    )
