"""旧路由请求入口，转发到 `ava.router_selector.request`。"""

from ava.router_selector.request import RouterRequestArtifacts, RouterRequestBuilder

__all__ = ["RouterRequestArtifacts", "RouterRequestBuilder"]
