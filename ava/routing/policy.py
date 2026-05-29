"""旧路由策略入口，转发到 `ava.router_selector.policy`。"""

from ava.router_selector.policy import RouterDecisionPolicy

__all__ = ["RouterDecisionPolicy"]
