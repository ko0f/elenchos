"""Pydantic DTOs for BFF request/response models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from elenchos.benchmarks.registry import SuiteSummary
from elenchos.benchmarks.schema import BenchmarkSuite, GenerationParamsDefaults
from elenchos.models import BenchmarkRef, Result, Run


class ProviderResponse(BaseModel):
    name: str
    base_url: str
    healthy: bool


class ModelsResponse(BaseModel):
    models: list[str]


class SuiteSummaryResponse(BaseModel):
    id: str
    version: int
    type: str
    description: str
    task_count: int
    source: str


class GenerationParamsResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    temperature: float = 0.0
    max_tokens: int | None = None
    top_p: float | None = None
    seed: int | None = None
    stop: list[str] | None = None


class SuiteDefaultsResponse(BaseModel):
    params: GenerationParamsResponse | None = None


class TaskResponse(BaseModel):
    id: str
    type: str
    prompt: str
    scorers: list[str]


class SuiteDetailResponse(BaseModel):
    id: str
    version: int
    type: str
    description: str
    defaults: SuiteDefaultsResponse | None = None
    tasks: list[TaskResponse]
    requires_code_exec: bool
    requires_judge: bool


class BenchmarkRefResponse(BaseModel):
    id: str
    version: int


class RunSummaryResponse(BaseModel):
    run_id: str
    started_at: str
    model: str
    benchmark: BenchmarkRefResponse | None = None
    finished_at: str | None = None
    summary: dict | None = None


class RunMetadataResponse(BaseModel):
    run_id: str
    started_at: str
    finished_at: str | None = None
    model: str
    params: dict
    tool_version: str
    benchmark: BenchmarkRefResponse | None = None
    summary: dict | None = None


class ResultResponse(BaseModel):
    task_id: str
    latency_ms: float
    prompt: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    output: str | None = None
    score: float | None = None
    scorer: str | None = None
    passed: int | None = None
    total: int | None = None
    finish_reason: str | None = None
    error: str | None = None


class RunDetailResponse(BaseModel):
    run: RunMetadataResponse
    results: list[ResultResponse]


def _suite_has_scorer(suite: BenchmarkSuite, scorer_type: str) -> bool:
    return any(
        scorer.type == scorer_type
        for task in suite.tasks
        for scorer in suite.effective_scoring(task)
    )


def _params_response(
    params: GenerationParamsDefaults | None,
) -> GenerationParamsResponse | None:
    if params is None:
        return None
    return GenerationParamsResponse.model_validate(params.model_dump())


def suite_summary_from_domain(summary: SuiteSummary) -> SuiteSummaryResponse:
    return SuiteSummaryResponse(
        id=summary.id,
        version=summary.version,
        type=summary.type,
        description=summary.description,
        task_count=summary.task_count,
        source=summary.source,
    )


def suite_detail_from_domain(suite: BenchmarkSuite) -> SuiteDetailResponse:
    defaults = None
    if suite.defaults is not None:
        defaults = SuiteDefaultsResponse(
            params=_params_response(suite.defaults.params),
        )

    tasks = [
        TaskResponse(
            id=task.id,
            type=suite.effective_task_type(task),
            prompt=task.prompt,
            scorers=[scorer.type for scorer in suite.effective_scoring(task)],
        )
        for task in suite.tasks
    ]

    return SuiteDetailResponse(
        id=suite.id,
        version=suite.version,
        type=suite.type,
        description=suite.description,
        defaults=defaults,
        tasks=tasks,
        requires_code_exec=_suite_has_scorer(suite, "unit_test"),
        requires_judge=_suite_has_scorer(suite, "judge_rubric"),
    )


def benchmark_ref_from_domain(ref: BenchmarkRef | None) -> BenchmarkRefResponse | None:
    if ref is None:
        return None
    return BenchmarkRefResponse(id=ref.id, version=ref.version)


def run_summary_from_domain(run: Run) -> RunSummaryResponse:
    return RunSummaryResponse(
        run_id=run.run_id,
        started_at=run.started_at,
        model=run.model,
        benchmark=benchmark_ref_from_domain(run.benchmark),
        finished_at=run.finished_at,
        summary=run.summary,
    )


def run_metadata_from_domain(run: Run) -> RunMetadataResponse:
    return RunMetadataResponse(
        run_id=run.run_id,
        started_at=run.started_at,
        finished_at=run.finished_at,
        model=run.model,
        params=run.params,
        tool_version=run.tool_version,
        benchmark=benchmark_ref_from_domain(run.benchmark),
        summary=run.summary,
    )


def result_from_domain(result: Result) -> ResultResponse:
    return ResultResponse.model_validate(result, from_attributes=True)
