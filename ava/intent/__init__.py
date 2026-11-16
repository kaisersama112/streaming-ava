"""多意图 / 技能子 Agent 协作层。

Router 产出意图与计划，本层负责把计划拆成可编排的子任务，
按串行 / 并行 / 条件分支调度技能子 Agent，并合并为一条统一回复。
"""

from .types import ExecutionPlan, IntentItem, OrchestrationOutcome, SubAgentResult
from .orchestrator import SkillOrchestrator, OrchestrationContext, PREDICATES
from .skills import SKILL_ASSETS, available_skills, skill_instructions

__all__ = [
    "ExecutionPlan",
    "IntentItem",
    "OrchestrationOutcome",
    "SubAgentResult",
    "SkillOrchestrator",
    "OrchestrationContext",
    "PREDICATES",
    "SKILL_ASSETS",
    "available_skills",
    "skill_instructions",
]