"""旧 LLM 请求入口，转发到 `ava.llm_model_executor.service`。"""

from ava.llm_model_executor.service import RequestPolicy

__all__ = [
    "RequestPolicy",
]
