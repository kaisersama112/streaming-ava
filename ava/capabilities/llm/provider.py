"""旧 LLM provider 入口，转发到 `ava.llm_model_executor.provider`。"""

from ava.llm_model_executor.provider import OpenAIResponsesProvider

__all__ = ["OpenAIResponsesProvider"]
