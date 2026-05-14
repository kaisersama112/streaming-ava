"""多模态对话流程中使用的媒体与轮次输入模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

# 支持的输入模态类型
Modality = Literal["text", "image", "audio", "video", "file"]


def _guess_audio_format(mime_type: str, name: str) -> str:
    """根据 MIME 类型和文件名推断音频格式。"""

    # 标准化 MIME 类型，便于后续匹配
    mime = mime_type.lower().strip()

    # MP3 格式判断
    if mime in {"audio/mpeg", "audio/mp3"} or name.lower().endswith(".mp3"):
        return "mp3"

    # WAV 格式判断
    if mime in {"audio/wav", "audio/x-wav"} or name.lower().endswith(".wav"):
        return "wav"

    # M4A / MP4 音频格式判断
    if mime in {"audio/mp4", "audio/m4a"} or name.lower().endswith((".m4a", ".mp4")):
        return "m4a"

    # OGG 格式判断
    if name.lower().endswith(".ogg"):
        return "ogg"

    # 兜底逻辑：
    # - 如果 MIME 类型形如 audio/xxx，则取斜杠后的部分
    # - 否则默认返回 wav
    return mime.split("/", 1)[-1] if "/" in mime else "wav"


@dataclass(frozen=True)
class MediaArtifact:
    """附加到单个用户轮次上的标准化媒体对象。"""

    # 媒体类型，例如 text、image、audio、video、file
    kind: Modality

    # 媒体名称，通常为文件名或展示名
    name: str

    # 媒体 MIME 类型，例如 image/png、audio/mpeg
    mime_type: str

    # 媒体摘要，通常来自上游解析、OCR、多模态理解或 metadata
    summary: str = ""

    # 内联数据地址，例如 base64 data URL；适合直接传给多模态模型
    data_url: str | None = None

    # 外部资源地址或内部存储 URI
    uri: str | None = None

    # 额外元数据，例如大小、页数、解析结果、缓存 key 等
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_prompt_dict(self) -> dict[str, Any]:
        """返回适合放入路由 prompt 的紧凑表示。"""

        payload: dict[str, Any] = {
            # 媒体类型
            "kind": self.kind,

            # 媒体名称
            "name": self.name,

            # MIME 类型
            "mime_type": self.mime_type,

            # 已有摘要
            "summary": self.summary,

            # 是否包含 data_url；只暴露布尔值，避免把大体积数据写入路由 prompt
            "has_data_url": bool(self.data_url),

            # 资源 URI，可用于追踪或后续读取
            "uri": self.uri,

            # 附加元数据
            "metadata": self.metadata,
        }

        return payload

    def to_message_block(self) -> dict[str, Any] | None:
        """在模型可直接消费时，返回 OpenAI 兼容的 content block。"""

        # 图片：使用 image_url block
        if self.kind == "image" and self.data_url:
            return {
                "type": "image_url",
                "image_url": {"url": self.data_url},
            }

        # 音频：使用 input_audio block，并推断音频格式
        if self.kind == "audio" and self.data_url:
            return {
                "type": "input_audio",
                "input_audio": {
                    "data": self.data_url,
                    "format": _guess_audio_format(self.mime_type, self.name),
                },
            }

        # 视频：使用 video block
        if self.kind == "video" and self.data_url:
            return {
                "type": "video",
                "video": [self.data_url],
            }

        # 其他类型，例如 file 或没有 data_url 的媒体，不能直接转为多模态 block
        return None

    def display_label(self) -> str:
        """返回适合展示在历史消息或摘要中的媒体标签。"""

        # 优先使用摘要；没有摘要时使用文件名
        base = self.summary.strip() or self.name

        # 标签格式示例：[image] 截图内容摘要
        return f"[{self.kind}] {base}"


@dataclass(frozen=True)
class TurnInput:
    """单个对话轮次的标准化用户输入。"""

    # 用户文本输入
    text: str = ""

    # 当前轮次携带的媒体附件
    artifacts: tuple[MediaArtifact, ...] = ()

    # 输入来源，例如 web、api、mobile 等
    source: str = "web"

    def normalized_text(self) -> str:
        """返回清理后的用户文本。"""

        # 兼容 text 被误传为 list 的情况，将列表元素拼接为字符串
        if isinstance(self.text, list):
            text_str = " ".join(self.text)
        else:
            text_str = str(self.text)

        # 合并连续空白，并去除首尾空白
        return " ".join(text_str.split()).strip()

    def multimodal_summary(self) -> str:
        """返回当前轮次的文本与附件综合摘要。"""

        parts: list[str] = []

        # 先写入用户文本
        text = self.normalized_text()
        if text:
            parts.append(f"用户文本: {text}")

        # 再写入附件展示标签
        for artifact in self.artifacts:
            label = artifact.display_label()

            # 如果附件有 URI，则追加 URI，便于追踪原始资源
            if artifact.uri:
                label = f"{label} ({artifact.uri})"

            parts.append(label)

        return "\n".join(parts).strip()

    def memory_text(self) -> str:
        """返回适合写入记忆系统的文本表示。"""

        # 优先使用多模态摘要；没有摘要时回退到纯文本；仍为空则返回“无”
        summary = self.multimodal_summary()
        return summary or self.normalized_text() or "无"

    def history_text(self) -> str:
        """返回适合写入历史消息的文本表示。"""

        # 当前轮次文本
        text = self.normalized_text()

        # 当前轮次附件标签
        artifact_lines = [
            artifact.display_label()
            for artifact in self.artifacts
        ]

        # 同时存在文本和附件时，将附件作为参考信息追加到文本后
        if text and artifact_lines:
            return (
                    f"{text}\n参考附件:\n"
                    + "\n".join(f"- {label}" for label in artifact_lines)
            )

        # 仅存在文本时，直接返回文本
        if text:
            return text

        # 仅存在附件时，返回附件列表
        if artifact_lines:
            return (
                    "参考附件:\n"
                    + "\n".join(f"- {label}" for label in artifact_lines)
            )

        # 文本和附件都没有时，使用 memory_text 兜底
        return self.memory_text()
