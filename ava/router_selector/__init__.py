"""路由选择模块。"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .policy import RouterDecisionPolicy
    from .request import RouterRequestArtifacts, RouterRequestBuilder
    from .schema import RouteDecision
    from .service import RouterResult, RouterService

__all__ = [
    "RouteDecision",
    "RouterDecisionPolicy",
    "RouterRequestArtifacts",
    "RouterRequestBuilder",
    "RouterResult",
    "RouterService",
]


def __getattr__(name: str):
    if name == "RouteDecision":
        from .schema import RouteDecision

        return RouteDecision
    if name == "RouterDecisionPolicy":
        from .policy import RouterDecisionPolicy

        return RouterDecisionPolicy
    if name in {"RouterRequestArtifacts", "RouterRequestBuilder"}:
        from .request import RouterRequestArtifacts, RouterRequestBuilder

        mapping = {
            "RouterRequestArtifacts": RouterRequestArtifacts,
            "RouterRequestBuilder": RouterRequestBuilder,
        }
        return mapping[name]
    if name in {"RouterResult", "RouterService"}:
        from .service import RouterResult, RouterService

        mapping = {
            "RouterResult": RouterResult,
            "RouterService": RouterService,
        }
        return mapping[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
