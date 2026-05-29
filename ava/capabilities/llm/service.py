"""旧 LLM 服务入口，转发到 `ava.llm_model_executor.service`。"""

from ava.llm_model_executor.service import LLMService, RequestContextBuilder

__all__ = [
    "LLMService",
    "RequestContextBuilder",
]
