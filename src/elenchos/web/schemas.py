"""Pydantic DTOs for BFF request/response models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

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
    description: str = ""
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


class CreateRunRequest(BaseModel):
    benchmark: str
    model: str
    temperature: float | None = None
    max_tokens: int | None = None
    concurrency: int | None = None
    allow_code_exec: bool = False
    judge: str | None = None


class CreateRunResponse(BaseModel):
    job_id: str
    run_id: str | None = None


class PromptRequest(BaseModel):
    model: str
    text: str


class PromptResponse(BaseModel):
    run_id: str
    output: str | None = None
    latency_ms: float
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    finish_reason: str | None = None
    error: str | None = None


class ProgressEventResponse(BaseModel):
    event: str
    data: dict


class CreateCompareRequest(BaseModel):
    run_ids: list[str]
    mode: str | None = None
    judge: str | None = None


class CreateCompareResponse(BaseModel):
    job_id: str
    comparison_id: str | None = None


class ComparisonSummaryResponse(BaseModel):
    comparison_id: str
    mode: str
    judge_model: str
    benchmark_id: str
    started_at: str
    finished_at: str | None = None
    run_ids: list[str]
    summary: dict | None = None


class TaskComparisonResponse(BaseModel):
    task_id: str
    prompt: str | None = None
    winner_run_id: str | None = None
    rationale: str | None = None
    scores: dict[str, float] = Field(default_factory=dict)


class ComparisonDetailResponse(BaseModel):
    comparison_id: str
    mode: str
    judge_model: str
    benchmark_id: str
    started_at: str
    finished_at: str | None = None
    runs: list[dict]
    tasks: list[TaskComparisonResponse]
    summary: dict | None = None


class ReportRequest(BaseModel):
    run_ids: list[str]
    format: str = "json"


class LeaderboardRowResponse(BaseModel):
    run_id: str
    model: str
    benchmark_id: str | None = None
    mean_score: float | None = None
    pass_rate: float | None = None
    p95_latency_ms: float | None = None
    task_count: int | None = None
    rank: int | None = None
    win_rate: float | None = None


class LeaderboardResponse(BaseModel):
    benchmark_id: str | None = None
    runs: list[LeaderboardRowResponse]


class JobStatusResponse(BaseModel):
    job_id: str
    kind: str
    status: str
    run_id: str | None = None
    comparison_id: str | None = None
    progress: list[ProgressEventResponse]
    result: dict | None = None
    error: str | None = None


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
            description=task.description,
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


def job_status_from_domain(job: object) -> JobStatusResponse:
    return JobStatusResponse(
        job_id=job.job_id,
        kind=job.kind,
        status=job.status,
        run_id=job.run_id,
        comparison_id=getattr(job, "comparison_id", None),
        progress=[
            ProgressEventResponse(event=item.event, data=item.data)
            for item in job.progress
        ],
        result=job.result,
        error=job.error,
    )


def comparison_summary_from_dict(payload: dict) -> ComparisonSummaryResponse:
    return ComparisonSummaryResponse(
        comparison_id=payload["comparison_id"],
        mode=payload["mode"],
        judge_model=payload["judge_model"],
        benchmark_id=payload["benchmark_id"],
        started_at=payload["started_at"],
        finished_at=payload.get("finished_at"),
        run_ids=payload.get("run_ids", []),
        summary=payload.get("summary"),
    )


def comparison_detail_from_dict(payload: dict) -> ComparisonDetailResponse:
    return ComparisonDetailResponse(
        comparison_id=payload["comparison_id"],
        mode=payload["mode"],
        judge_model=payload["judge_model"],
        benchmark_id=payload["benchmark_id"],
        started_at=payload["started_at"],
        finished_at=payload.get("finished_at"),
        runs=payload.get("runs", []),
        tasks=[
            TaskComparisonResponse.model_validate(task)
            for task in payload.get("tasks", [])
        ],
        summary=payload.get("summary"),
    )


def leaderboard_from_domain(report) -> LeaderboardResponse:
    return LeaderboardResponse(
        benchmark_id=report.benchmark_id,
        runs=[
            LeaderboardRowResponse(
                run_id=row.run_id,
                model=row.model,
                benchmark_id=row.benchmark_id,
                mean_score=row.mean_score,
                pass_rate=row.pass_rate,
                p95_latency_ms=row.p95_latency_ms,
                task_count=row.task_count,
                rank=row.rank,
                win_rate=row.win_rate,
            )
            for row in report.rows
        ],
    )
