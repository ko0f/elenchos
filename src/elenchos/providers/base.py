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
    reasoning_effort: str | None = None


@dataclass
class Completion:
    text: str
    prompt_tokens: int | None
    completion_tokens: int | None
    latency_ms: float
    raw: dict
    finish_reason: str | None
    reasoning: str | None = None


def format_model_output(*, text: str, reasoning: str | None = None) -> str:
    """Build persisted/display text from answer + optional reasoning trace."""
    reasoning_text = reasoning.strip() if isinstance(reasoning, str) else ""
    if not reasoning_text:
        return text
    parts = [f"## Reasoning\n\n{reasoning_text}"]
    if text.strip():
        parts.append(f"## Output\n\n{text.rstrip()}")
    else:
        parts.append("## Output\n\n(no answer — model hit token limit during reasoning)")
    return "\n\n".join(parts)


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
