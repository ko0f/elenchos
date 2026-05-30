"""Baseline-relative scoring over stored per-task scores or judge quality."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from elenchos.config import ElenchosSettings
from elenchos.models import Result
from elenchos.storage import (
    find_comparison,
    find_run,
    get_baseline_comparison_id,
    get_baseline_entry,
    get_baseline_run_id,
    list_comparisons,
    load_results,
    read_baseline_score,
    write_baseline_score,
)

logger = logging.getLogger(__name__)

_CACHE_METHOD_STORED = "stored"
_CACHE_METHOD_COMPARISON = "comparison"


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
    score_method: str = _CACHE_METHOD_STORED
    comparison_id: str | None = None


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


def benchmark_prefers_judge_baseline(
    benchmark_id: str,
    settings: ElenchosSettings | None = None,
) -> bool:
    """Coding-style suites (unit_test) need judge scoring for meaningful vs baseline."""
    from elenchos.benchmarks.registry import resolve_benchmark

    suite = resolve_benchmark(benchmark_id, settings=settings)
    for task in suite.tasks:
        for scorer in suite.effective_scoring(task):
            if scorer.type == "unit_test":
                return True
    return False


def _compute_stored_baseline_comparison(
    *,
    run_dir,
    run,
    baseline_dir,
    baseline_run,
    baseline_run_id: str,
    computed_at: str,
) -> BaselineComparison:
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
        score_method=_CACHE_METHOD_STORED,
    )


def _comparison_run_ids(payload: dict) -> list[str]:
    return [
        str(item["run_id"])
        for item in payload.get("runs", [])
        if item.get("run_id")
    ]


def _resolve_comparison_payload(
    benchmark_id: str,
    run_id: str,
    settings: ElenchosSettings | None = None,
) -> tuple[dict, str] | None:
    """Pinned comparison, else newest rubric comparison that includes run_id."""
    pinned = get_baseline_comparison_id(benchmark_id, settings)
    if pinned:
        found = find_comparison(pinned, settings)
        if found is not None:
            _path, payload = found
            if payload.get("benchmark_id") == benchmark_id and run_id in _comparison_run_ids(
                payload
            ):
                return payload, pinned

    for summary in list_comparisons(settings):
        if summary.get("benchmark_id") != benchmark_id:
            continue
        if summary.get("mode") != "rubric":
            continue
        comparison_id = summary.get("comparison_id")
        if not comparison_id or run_id not in (summary.get("run_ids") or []):
            continue
        found = find_comparison(comparison_id, settings)
        if found is not None:
            return found[1], comparison_id
    return None


def compute_comparison_baseline_comparison(
    run_id: str,
    settings: ElenchosSettings | None = None,
) -> BaselineComparison | None:
    """Derive vs-baseline from a persisted rubric comparison artifact."""
    found = find_run(run_id, settings)
    if found is None:
        return None
    _run_dir, run = found
    if run.benchmark is None:
        return None

    benchmark_id = run.benchmark.id
    baseline_run_id = get_baseline_run_id(benchmark_id, settings)
    if baseline_run_id is None:
        return None

    computed_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    baseline_found = find_run(baseline_run_id, settings)
    if baseline_found is None:
        return None
    _baseline_dir, baseline_run = baseline_found

    if run_id == baseline_run_id:
        return BaselineComparison(
            baseline_run_id=baseline_run_id,
            baseline_model=baseline_run.model,
            relative_score=1.0,
            is_baseline=True,
            tasks=[],
            computed_at=computed_at,
        )

    resolved = _resolve_comparison_payload(benchmark_id, run_id, settings)
    if resolved is None:
        return None
    payload, comparison_id = resolved
    computed_at = payload.get("finished_at") or payload.get("started_at") or computed_at

    run_ids = _comparison_run_ids(payload)
    baseline_scores: dict[str, float] = {}
    candidate_scores: dict[str, float] = {}
    tasks: list[BaselineTask] = []

    if baseline_run_id in run_ids and run_id in run_ids:
        for task in payload.get("tasks", []):
            task_id = task.get("task_id")
            scores = task.get("scores") or {}
            if task_id is None or baseline_run_id not in scores or run_id not in scores:
                continue
            base_score = float(scores[baseline_run_id])
            cand_score = float(scores[run_id])
            baseline_scores[task_id] = base_score
            candidate_scores[task_id] = cand_score
            tasks.append(
                BaselineTask(
                    task_id=task_id,
                    baseline_score=base_score,
                    score=cand_score,
                    delta=cand_score - base_score,
                )
            )
        relative = _relative_score(baseline_scores, candidate_scores)
    elif run_id in run_ids:
        mean_scores = (payload.get("summary") or {}).get("mean_score") or {}
        relative = mean_scores.get(run_id)
        if relative is not None:
            relative = float(relative)
        for task in payload.get("tasks", []):
            task_id = task.get("task_id")
            scores = task.get("scores") or {}
            if task_id is None or run_id not in scores:
                continue
            cand_score = float(scores[run_id])
            candidate_scores[task_id] = cand_score
            tasks.append(
                BaselineTask(
                    task_id=task_id,
                    baseline_score=1.0,
                    score=cand_score,
                    delta=cand_score - 1.0,
                )
            )
        logger.info(
            "Comparison %s has no baseline run %s; using mean rubric score for %s",
            comparison_id,
            baseline_run_id,
            run_id,
        )
    else:
        return None

    return BaselineComparison(
        baseline_run_id=baseline_run_id,
        baseline_model=baseline_run.model,
        relative_score=relative,
        is_baseline=False,
        tasks=tasks,
        computed_at=computed_at,
        score_method=_CACHE_METHOD_COMPARISON,
        comparison_id=comparison_id,
    )


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

    if benchmark_prefers_judge_baseline(benchmark_id, settings):
        return compute_comparison_baseline_comparison(run_id, settings)

    return _compute_stored_baseline_comparison(
        run_dir=run_dir,
        run=run,
        baseline_dir=baseline_dir,
        baseline_run=baseline_run,
        baseline_run_id=baseline_run_id,
        computed_at=computed_at,
    )


def _expected_cache_method(benchmark_id: str, settings: ElenchosSettings | None) -> str:
    if benchmark_prefers_judge_baseline(benchmark_id, settings):
        return _CACHE_METHOD_COMPARISON
    return _CACHE_METHOD_STORED


def _comparison_to_cache_payload(
    comparison: BaselineComparison,
    *,
    method: str,
    comparison_id: str | None = None,
) -> dict:
    payload = {
        "method": method,
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
    if comparison_id:
        payload["comparison_id"] = comparison_id
    return payload


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


def _cache_is_stale(
    cached: dict,
    *,
    benchmark_id: str,
    is_baseline: bool,
    settings: ElenchosSettings | None,
) -> bool:
    if not is_baseline and cached.get("relative_score") is None:
        return True
    expected = _expected_cache_method(benchmark_id, settings)
    cached_method = cached.get("method", _CACHE_METHOD_STORED)
    if cached_method != expected:
        return True
    pinned = get_baseline_comparison_id(benchmark_id, settings)
    if pinned and cached.get("comparison_id") != pinned:
        return True
    return False


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
        if not _cache_is_stale(
            cached,
            benchmark_id=benchmark_id,
            is_baseline=is_baseline,
            settings=settings,
        ):
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
        write_baseline_score(
            run_dir,
            _comparison_to_cache_payload(
                comparison,
                method=comparison.score_method,
                comparison_id=comparison.comparison_id,
            ),
        )
    return comparison
