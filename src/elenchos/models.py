from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime


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
