from __future__ import annotations

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


def generation_params_to_dict(params: GenerationParams) -> dict:
    payload: dict = {"temperature": params.temperature, "top_p": params.top_p}
    if params.max_tokens is not None:
        payload["max_tokens"] = params.max_tokens
    if params.seed is not None:
        payload["seed"] = params.seed
    if params.stop is not None:
        payload["stop"] = params.stop
    return payload


@dataclass
class BenchmarkRef:
    id: str
    version: int = 1

    def to_dict(self) -> dict:
        return {"id": self.id, "version": self.version}

    @staticmethod
    def from_dict(payload: dict | None) -> BenchmarkRef | None:
        if not payload:
            return None
        return BenchmarkRef(
            id=str(payload["id"]),
            version=int(payload.get("version", 1)),
        )


@dataclass
class Run:
    run_id: str
    started_at: str
    model: str
    params: dict
    tool_version: str
    finished_at: str | None = None
    benchmark: BenchmarkRef | None = None
    summary: dict | None = None
    dir_name: str | None = None

    def to_dict(self) -> dict:
        payload: dict = {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "model": self.model,
            "params": self.params,
            "tool_version": self.tool_version,
        }
        if self.finished_at is not None:
            payload["finished_at"] = self.finished_at
        if self.benchmark is not None:
            payload["benchmark"] = self.benchmark.to_dict()
        if self.summary is not None:
            payload["summary"] = self.summary
        return payload

    @staticmethod
    def from_dict(payload: dict) -> Run:
        return Run(
            run_id=str(payload["run_id"]),
            started_at=str(payload["started_at"]),
            finished_at=payload.get("finished_at"),
            benchmark=BenchmarkRef.from_dict(payload.get("benchmark")),
            model=str(payload["model"]),
            params=dict(payload.get("params") or {}),
            tool_version=str(payload.get("tool_version", "")),
            summary=payload.get("summary"),
        )


@dataclass
class Result:
    task_id: str
    latency_ms: float
    prompt: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    output_ref: str | None = None
    output: str | None = None
    score: float | None = None
    scorer: str | None = None
    passed: int | None = None
    total: int | None = None
    finish_reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        payload: dict = {
            "task_id": self.task_id,
            "latency_ms": self.latency_ms,
        }
        optional_fields = {
            "prompt": self.prompt,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "output_ref": self.output_ref,
            "score": self.score,
            "scorer": self.scorer,
            "passed": self.passed,
            "total": self.total,
            "finish_reason": self.finish_reason,
            "error": self.error,
        }
        for key, value in optional_fields.items():
            if value is not None:
                payload[key] = value
        return payload

    @staticmethod
    def from_dict(payload: dict) -> Result:
        return Result(
            task_id=str(payload["task_id"]),
            latency_ms=float(payload["latency_ms"]),
            prompt=payload.get("prompt"),
            prompt_tokens=payload.get("prompt_tokens"),
            completion_tokens=payload.get("completion_tokens"),
            output_ref=payload.get("output_ref"),
            score=payload.get("score"),
            scorer=payload.get("scorer"),
            passed=payload.get("passed"),
            total=payload.get("total"),
            finish_reason=payload.get("finish_reason"),
            error=payload.get("error"),
        )


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
