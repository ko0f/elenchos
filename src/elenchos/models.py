from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

from elenchos.providers.base import GenerationParams, Message


@dataclass(frozen=True)
class ModelId:
    provider: str
    model: str

    @property
    def qualified(self) -> str:
        return f"{self.provider}/{self.model}"


def parse_model_id(value: str) -> ModelId:
    """Parse ``provider/model`` identifiers (model may contain slashes)."""
    value = value.strip()
    if "/" not in value:
        raise ValueError(
            f"Invalid model id {value!r}: expected format provider/model"
        )

    provider, model = value.split("/", 1)
    if not provider or not model:
        raise ValueError(
            f"Invalid model id {value!r}: expected format provider/model"
        )

    return ModelId(provider=provider, model=model)


def build_messages(
    prompt: str,
    *,
    system: str | None = None,
) -> list[Message]:
    messages: list[Message] = []
    if system:
        messages.append(Message(role="system", content=system))
    messages.append(Message(role="user", content=prompt))
    return messages


def default_generation_params() -> GenerationParams:
    return GenerationParams(temperature=0.0, max_tokens=1024)


@dataclass
class PromptCase:
    id: str
    prompt: str
    metadata: dict = field(default_factory=dict)


@dataclass
class RunResult:
    case_id: str
    prompt: str
    response: str
    model: str
    latency_ms: float
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class BenchmarkReport:
    model: str
    base_url: str
    started_at: str
    finished_at: str
    results: list[RunResult] = field(default_factory=list)

    @staticmethod
    def now_iso() -> str:
        return datetime.now(UTC).isoformat()

    def to_dict(self) -> dict:
        return {
            "model": self.model,
            "base_url": self.base_url,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "results": [result.to_dict() for result in self.results],
        }
