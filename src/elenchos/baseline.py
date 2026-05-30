"""Baseline-relative scoring over stored per-task scores."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from elenchos.config import ElenchosSettings
from elenchos.models import Result
from elenchos.storage import (
    find_run,
    get_baseline_run_id,
    load_results,
    read_baseline_score,
    write_baseline_score,
)


@dataclass
class BaselineTask:
    task_id: str
    baseline_score: float
    score: float
    delta: float


@dataclass
class BaselineComparison:
    baseline_run_id: str
    baseline_model: str
    relative_score: float | None
    is_baseline: bool
    tasks: list[BaselineTask]
    computed_at: str


def _scored_task_scores(results: list[Result]) -> dict[str, float]:
    scores: dict[str, float] = {}
    for result in results:
        if result.error is None and result.score is not None:
            scores[result.task_id] = result.score
    return scores


def _relative_score(
    baseline_scores: dict[str, float],
    candidate_scores: dict[str, float],
) -> float | None:
    shared = set(baseline_scores) & set(candidate_scores)
    if not shared:
        return None
    baseline_sum = sum(baseline_scores[task_id] for task_id in shared)
    if baseline_sum == 0:
        return None
    candidate_sum = sum(candidate_scores[task_id] for task_id in shared)
    return candidate_sum / baseline_sum


def compute_baseline_comparison(
    run_id: str,
    settings: ElenchosSettings | None = None,
) -> BaselineComparison | None:
    found = find_run(run_id, settings)
    if found is None:
        return None
    run_dir, run = found
    if run.benchmark is None:
        return None

    benchmark_id = run.benchmark.id
    baseline_run_id = get_baseline_run_id(benchmark_id, settings)
    if baseline_run_id is None:
        return None

    computed_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")

    if run_id == baseline_run_id:
        return BaselineComparison(
            baseline_run_id=baseline_run_id,
            baseline_model=run.model,
            relative_score=1.0,
            is_baseline=True,
            tasks=[],
            computed_at=computed_at,
        )

    baseline_found = find_run(baseline_run_id, settings)
    if baseline_found is None:
        return None
    baseline_dir, baseline_run = baseline_found

    candidate_scores = _scored_task_scores(
        load_results(run_dir, include_output=False)
    )
    baseline_scores = _scored_task_scores(
        load_results(baseline_dir, include_output=False)
    )
    shared = sorted(set(baseline_scores) & set(candidate_scores))
    relative = _relative_score(baseline_scores, candidate_scores)
    tasks = [
        BaselineTask(
            task_id=task_id,
            baseline_score=baseline_scores[task_id],
            score=candidate_scores[task_id],
            delta=candidate_scores[task_id] - baseline_scores[task_id],
        )
        for task_id in shared
    ]

    return BaselineComparison(
        baseline_run_id=baseline_run_id,
        baseline_model=baseline_run.model,
        relative_score=relative,
        is_baseline=False,
        tasks=tasks,
        computed_at=computed_at,
    )


def _comparison_to_cache_payload(comparison: BaselineComparison) -> dict:
    return {
        "baseline_run_id": comparison.baseline_run_id,
        "relative_score": comparison.relative_score,
        "computed_at": comparison.computed_at,
        "tasks": [
            {
                "task_id": task.task_id,
                "baseline_score": task.baseline_score,
                "score": task.score,
                "delta": task.delta,
            }
            for task in comparison.tasks
        ],
    }


def _cache_to_comparison(
    payload: dict,
    *,
    baseline_model: str,
    is_baseline: bool,
) -> BaselineComparison:
    tasks = [
        BaselineTask(
            task_id=item["task_id"],
            baseline_score=item["baseline_score"],
            score=item["score"],
            delta=item["delta"],
        )
        for item in payload.get("tasks", [])
    ]
    return BaselineComparison(
        baseline_run_id=payload["baseline_run_id"],
        baseline_model=baseline_model,
        relative_score=payload.get("relative_score"),
        is_baseline=is_baseline,
        tasks=tasks,
        computed_at=payload["computed_at"],
    )


def get_or_compute_baseline_comparison(
    run_id: str,
    settings: ElenchosSettings | None = None,
) -> BaselineComparison | None:
    found = find_run(run_id, settings)
    if found is None:
        return None
    run_dir, run = found
    if run.benchmark is None:
        return None

    benchmark_id = run.benchmark.id
    baseline_run_id = get_baseline_run_id(benchmark_id, settings)
    if baseline_run_id is None:
        return None

    is_baseline = run_id == baseline_run_id
    cached = read_baseline_score(run_dir)
    if cached is not None and cached.get("baseline_run_id") == baseline_run_id:
        baseline_found = find_run(baseline_run_id, settings)
        baseline_model = (
            baseline_found[1].model if baseline_found is not None else ""
        )
        return _cache_to_comparison(
            cached,
            baseline_model=baseline_model,
            is_baseline=is_baseline,
        )

    comparison = compute_baseline_comparison(run_id, settings)
    if comparison is not None:
        write_baseline_score(run_dir, _comparison_to_cache_payload(comparison))
    return comparison
