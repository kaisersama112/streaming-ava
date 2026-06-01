"""多模态领域模型。

当前该模块只保留正式需要的媒体对象 `MediaArtifact`。
旧输入对象已不再作为正式输入模型参与主流程。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Modality = Literal["text", "image", "audio", "video", "file"]


def _guess_audio_format(mime_type: str, name: str) -> str:
    """根据 MIME 类型和文件名推断音频格式。"""
    mime = mime_type.lower().strip()
    if mime in {"audio/mpeg", "audio/mp3"} or name.lower().endswith(".mp3"):
        return "mp3"
    if mime in {"audio/wav", "audio/x-wav"} or name.lower().endswith(".wav"):
        return "wav"
    if mime in {"audio/mp4", "audio/m4a"} or name.lower().endswith((".m4a", ".mp4")):
        return "m4a"
    if name.lower().endswith(".ogg"):
        return "ogg"
    return mime.split("/", 1)[-1] if "/" in mime else "wav"


@dataclass(frozen=True)
class MediaArtifact:
    """附加到单个用户轮次上的标准化媒体对象。"""

    kind: Modality
    name: str
    mime_type: str
    summary: str = ""
    data_url: str | None = None
    uri: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_prompt_dict(self) -> dict[str, Any]:
        """返回适合放入路由 prompt 的紧凑表示。"""
        return {
            "kind": self.kind,
            "name": self.name,
            "mime_type": self.mime_type,
            "summary": self.summary,
            "has_data_url": bool(self.data_url),
            "uri": self.uri,
            "metadata": self.metadata,
        }

    def to_message_block(self) -> dict[str, Any] | None:
        """在模型可直接消费时，返回兼容的 content block。"""
        if self.kind == "image" and self.data_url:
            return {
                "type": "image_url",
                "image_url": {"url": self.data_url},
            }
        if self.kind == "audio" and self.data_url:
            return {
                "type": "input_audio",
                "input_audio": {
                    "data": self.data_url,
                    "format": _guess_audio_format(self.mime_type, self.name),
                },
            }
        if self.kind == "video" and self.data_url:
            return {
                "type": "video",
                "video": [self.data_url],
            }
        return None

    def display_label(self) -> str:
        """返回适合展示在历史消息或摘要中的媒体标签。"""
        base = self.summary.strip() or self.name
        return f"[{self.kind}] {base}"
