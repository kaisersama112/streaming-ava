"""生成流水线旧回复入口的薄转发层。

正式实现已经统一收敛到 `ava.inference_runtime.service`。
这里保留旧模块路径，仅用于把历史调用转发到新四层中的推理运行时。
"""

from ava.inference_runtime.service import (
    ReplyExecutionResult,
    generate_reply_sync,
    stream_reply_with_callbacks,
)

__all__ = [
    "ReplyExecutionResult",
    "generate_reply_sync",
    "stream_reply_with_callbacks",
]
