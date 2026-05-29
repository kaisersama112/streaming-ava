"""旧路由入口，转发到 `ava.router_selector`。"""

from ava.router_selector import RouteDecision, RouterDecisionPolicy, RouterResult, RouterService

__all__ = [
    "RouteDecision",
    "RouterDecisionPolicy",
    "RouterResult",
    "RouterService",
]
