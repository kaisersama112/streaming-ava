"""旧 LLM provider 入口，转发到 `ava.llm_model_executor.service`。"""

from ava.llm_model_executor.service import OpenAIResponsesProvider

__all__ = ["OpenAIResponsesProvider"]
