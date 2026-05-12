"""SDK interface exports."""

__all__ = ["AgentsExecutionResult", "run_agents_sdk_stream", "run_agents_sdk_sync"]


def __getattr__(name: str):
    if name in {"AgentsExecutionResult", "run_agents_sdk_stream", "run_agents_sdk_sync"}:
        from ava.pipeline.agent import AgentsExecutionResult, run_agents_sdk_stream, run_agents_sdk_sync
        mapping = {
            "AgentsExecutionResult": AgentsExecutionResult,
            "run_agents_sdk_stream": run_agents_sdk_stream,
            "run_agents_sdk_sync": run_agents_sdk_sync,
        }
        return mapping[name]
    raise AttributeError(name)
