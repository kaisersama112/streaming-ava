from dataclasses import dataclass


class InferenceEvent:
    pass


@dataclass(frozen=True)
class OutputTextDelta(InferenceEvent):
    text: str


@dataclass(frozen=True)
class InferenceCompleted(InferenceEvent):
    text: str
    finish_reason: str | None = None


@dataclass(frozen=True)
class InferenceError(InferenceEvent):
    error: str

