"""Optional OpenAI Agents SDK execution path.

The normal responder path is a direct chat/streaming call. This package is a
drop-in execution backend for selected turns where tool use, specialist agents,
or state patch proposals are useful. Imports are lazy so projects without the
Agents SDK installed can still use the rest of the pipeline.
"""

__all__ = [
    "AgentsExecutionResult",
    "clear_agent_session",
    "clear_agent_session_async",
    "run_agents_sdk_stream",
    "run_agents_sdk_sync",
]


def __getattr__(name: str):
    if name in {"clear_agent_session", "clear_agent_session_async"}:
        from ava.pipeline.agent.sessions import clear_agent_session, clear_agent_session_async

        mapping = {
            "clear_agent_session": clear_agent_session,
            "clear_agent_session_async": clear_agent_session_async,
        }
        return mapping[name]

    if name in {"AgentsExecutionResult", "run_agents_sdk_stream", "run_agents_sdk_sync"}:
        from ava.pipeline.agent.executor import (
            AgentsExecutionResult,
            run_agents_sdk_stream,
            run_agents_sdk_sync,
        )

        mapping = {
            "AgentsExecutionResult": AgentsExecutionResult,
            "run_agents_sdk_stream": run_agents_sdk_stream,
            "run_agents_sdk_sync": run_agents_sdk_sync,
        }
        return mapping[name]

    raise AttributeError(name)
