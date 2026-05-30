from dataclasses import dataclass
from typing import Protocol


@dataclass
class Message:
    role: str
    content: str


@dataclass
class GenerationParams:
    temperature: float = 0.0
    top_p: float = 1.0
    max_tokens: int | None = None
    seed: int | None = None
    stop: list[str] | None = None


@dataclass
class Completion:
    text: str
    prompt_tokens: int | None
    completion_tokens: int | None
    latency_ms: float
    raw: dict
    finish_reason: str | None


class Provider(Protocol):
    name: str

    def list_models(self) -> list[str]: ...

    def complete(
        self,
        model: str,
        messages: list[Message],
        params: GenerationParams,
    ) -> Completion: ...

    def health_check(self) -> bool: ...
