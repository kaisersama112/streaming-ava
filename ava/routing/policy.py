"""旧路由策略入口，转发到 `ava.router_selector.service`。"""

from ava.router_selector.service import RouterDecisionPolicy

__all__ = ["RouterDecisionPolicy"]
