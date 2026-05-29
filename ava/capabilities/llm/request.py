"""旧 LLM 请求入口，转发到 `ava.llm_model_executor.request`。"""

from ava.llm_model_executor.request import InferenceRequestBuilder, RequestPolicy

__all__ = [
    "InferenceRequestBuilder",
    "RequestPolicy",
]
