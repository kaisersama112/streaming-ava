"""Shared application data structures for orchestration outputs."""

from dataclasses import dataclass

from ava.domain.routing import RouteDecision
from ava.domain.strategy import BranchStrategy


@dataclass
class TurnPlan:
    decision: RouteDecision
    orchestrator_name: str
    strategy: BranchStrategy
    responder_messages: list[dict[str, object]]
