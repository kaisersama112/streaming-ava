"""旧路由服务入口，转发到 `ava.router_selector.service`。"""

from ava.router_selector.service import RouterResult, RouterService

__all__ = ["RouterResult", "RouterService"]
