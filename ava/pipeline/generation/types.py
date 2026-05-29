"""Shared application data structures for orchestration outputs."""

from dataclasses import dataclass
from typing import Any

from ava.router_selector.schema import RouteDecision
from ava.domain.conversation.strategy import BranchStrategy


@dataclass
class TurnPlan:
    decision: RouteDecision
    orchestrator_name: str
    strategy: BranchStrategy
    responder_messages: list[dict[str, object]]
    router_plan: dict[str, Any] | None = None
