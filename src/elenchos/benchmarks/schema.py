"""Pydantic models for benchmark suite YAML."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SuiteValidationError(ValueError):
    """Benchmark YAML failed schema validation."""


# Default completion budget for runs (reasoning models can use most of this).
DEFAULT_MAX_TOKENS = 131_072


class GenerationParamsDefaults(BaseModel):
    model_config = ConfigDict(extra="forbid")

    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=DEFAULT_MAX_TOKENS, ge=1)
    top_p: float | None = Field(default=None, ge=0.0, le=1.0)
    seed: int | None = None
    stop: list[str] | None = None


class ExactMatchScorer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["exact_match"]
    expected: str


class RegexMatchScorer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["regex_match"]
    pattern: str


class ContainsAllScorer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["contains_all"]
    strings: list[str] = Field(min_length=1)


class UnitTestScorer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["unit_test"]
    language: Literal["python"] = "python"
    entrypoint: str
    tests: str


class JudgeRubricScorer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["judge_rubric"]
    rubric: str


class MetricsScorer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["metrics"]


ScorerConfig = Annotated[
    ExactMatchScorer
    | RegexMatchScorer
    | ContainsAllScorer
    | UnitTestScorer
    | JudgeRubricScorer
    | MetricsScorer,
    Field(discriminator="type"),
]


class SuiteDefaults(BaseModel):
    model_config = ConfigDict(extra="forbid")

    params: GenerationParamsDefaults | None = None
    scoring: list[ScorerConfig] = Field(default_factory=list)


class Task(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    description: str = ""
    prompt: str = Field(min_length=1)
    type: Literal["text", "coding"] | None = None
    scoring: list[ScorerConfig] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("task id must not be blank")
        return cleaned


class BenchmarkSuite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    version: int = Field(ge=1)
    type: Literal["text", "coding"]
    description: str = ""
    defaults: SuiteDefaults | None = None
    tasks: list[Task] = Field(min_length=1)

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("suite id must not be blank")
        return cleaned

    @model_validator(mode="after")
    def unique_task_ids(self) -> BenchmarkSuite:
        seen: set[str] = set()
        duplicates: list[str] = []
        for task in self.tasks:
            if task.id in seen:
                duplicates.append(task.id)
            seen.add(task.id)
        if duplicates:
            joined = ", ".join(sorted(set(duplicates)))
            raise ValueError(f"duplicate task ids: {joined}")
        return self

    def effective_task_type(self, task: Task) -> str:
        return task.type or self.type

    def effective_scoring(self, task: Task) -> list[ScorerConfig]:
        if task.scoring:
            return task.scoring
        if self.defaults and self.defaults.scoring:
            return self.defaults.scoring
        return []


def format_validation_errors(errors: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for error in errors:
        location = ".".join(str(part) for part in error.get("loc", ()))
        message = error.get("msg", "invalid value")
        if location:
            lines.append(f"  {location}: {message}")
        else:
            lines.append(f"  {message}")
    return "\n".join(lines)
