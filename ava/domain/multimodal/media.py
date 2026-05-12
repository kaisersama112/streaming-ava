"""Media and turn input models used by the multimodal conversation flow."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Modality = Literal["text", "image", "audio", "video", "file"]


def _guess_audio_format(mime_type: str, name: str) -> str:
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
    """A normalized media item attached to one user turn."""

    kind: Modality
    name: str
    mime_type: str
    summary: str = ""
    data_url: str | None = None
    uri: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_prompt_dict(self) -> dict[str, Any]:
        """Return a compact representation safe for router prompts."""
        payload: dict[str, Any] = {
            "kind": self.kind,
            "name": self.name,
            "mime_type": self.mime_type,
            "summary": self.summary,
            "has_data_url": bool(self.data_url),
            "uri": self.uri,
            "metadata": self.metadata,
        }
        return payload

    def to_message_block(self) -> dict[str, Any] | None:
        """Return an OpenAI-compatible content block when the model can use it."""
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
        base = self.summary.strip() or self.name
        return f"[{self.kind}] {base}"


@dataclass(frozen=True)
class TurnInput:
    """Normalized user input for one conversation turn."""

    text: str = ""
    artifacts: tuple[MediaArtifact, ...] = ()
    source: str = "web"

    def normalized_text(self) -> str:
        if isinstance(self.text, list):
            text_str = " ".join(self.text)
        else:
            text_str = str(self.text)
        return " ".join(text_str.split()).strip()

    def multimodal_summary(self) -> str:
        parts: list[str] = []
        text = self.normalized_text()
        if text:
            parts.append(f"用户文本: {text}")
        for artifact in self.artifacts:
            label = artifact.display_label()
            if artifact.uri:
                label = f"{label} ({artifact.uri})"
            parts.append(label)
        return "\n".join(parts).strip()

    def memory_text(self) -> str:
        summary = self.multimodal_summary()
        return summary or self.normalized_text() or "无"

    def history_text(self) -> str:
        text = self.normalized_text()
        artifact_lines = [artifact.display_label() for artifact in self.artifacts]
        if text and artifact_lines:
            return f"{text}\n参考附件:\n" + "\n".join(f"- {label}" for label in artifact_lines)
        if text:
            return text
        if artifact_lines:
            return "参考附件:\n" + "\n".join(f"- {label}" for label in artifact_lines)
        return self.memory_text()
