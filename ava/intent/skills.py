"""技能子 Agent 池：解题 / 批改 / 讲解 / 学情评估。

每个技能绑定 prompt-plugin 中的 task 资产，子 Agent 的系统指令直接来自资产，
保证「提示词即技能定义」，不在代码里硬编码教学规则。
"""

from __future__ import annotations

from typing import Any

from ava.capabilities.prompt.prompt_loader import PromptCenter

SKILL_ASSETS: dict[str, str] = {
    "solve": "components/task/solve/SKILL.md",
    "check": "components/task/check/SKILL.md",
    "explain": "components/task/explain/SKILL.md",
    "assess": "components/task/assess/SKILL.md",
}

SKILL_DESCRIPTIONS: dict[str, str] = {
    "solve": "解题：重建题意、选方法、推进当前最需要的一步",
    "check": "批改：判断学生作答对错，指出最关键依据与最小修正",
    "explain": "讲解：把概念/步骤讲清楚，按学生水平控制粒度",
    "assess": "学情评估：判断掌握程度，给出下一步学习建议",
}

EDUCATION_SKILLS = tuple(SKILL_ASSETS)


def available_skills() -> list[str]:
    return list(SKILL_ASSETS)


def skill_instructions(prompt_center: PromptCenter | None, skill: str) -> str:
    """读取技能资产正文（PromptCenter 内部已按资产 mtime 缓存）。"""
    name = str(skill or "").strip().replace("_", "-")
    asset_path = SKILL_ASSETS.get(name)
    if not asset_path:
        return ""
    center = prompt_center or _default_center()
    skill_obj = center.load_skill(asset_path)
    parts = [f"# 技能：{skill_obj.name}", skill_obj.purpose.strip(), skill_obj.instructions.strip()]
    return "\n\n".join(part for part in parts if part)


def _default_center() -> PromptCenter:
    from ava.capabilities.prompt.factories import build_prompt_center

    return build_prompt_center()


def skill_tool_description(skill: str) -> str:
    name = str(skill or "").strip()
    return SKILL_DESCRIPTIONS.get(name, f"技能子 Agent：{name}")


def build_subagent_instructions(
    prompt_center: PromptCenter | None,
    skill: str,
    *,
    runtime_section: str = "",
    extra_rules: str = "",
) -> str:
    """子 Agent 完整系统指令 = 技能资产 + 只读运行时事实 + 协作约束。"""
    body = skill_instructions(prompt_center, skill)
    if not body:
        body = f"# 技能：{skill}\n按当前轮计划完成该技能任务，输出简洁中文。"
    constraints = (
        "# 协作约束\n"
        "- 你是技能子 Agent，只完成分配给你的子任务，不重写整轮回复。\n"
        "- 输出纯文本正文，不要输出 JSON、不要复述任务编号。\n"
        "- 需要更新会话状态时，只能调用 note_state_patch 提交白名单字段建议。\n"
        "- 运行时状态是只读事实，禁止改写或臆造。"
    )
    parts = [body, constraints]
    if runtime_section:
        parts.append(runtime_section)
    if extra_rules:
        parts.append(extra_rules)
    return "\n\n".join(parts)