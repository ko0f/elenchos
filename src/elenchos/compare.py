"""Compare benchmark runs using a judge LLM."""

from __future__ import annotations

import logging
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from elenchos.config import BUILTIN_PROVIDERS, ElenchosSettings, resolve_judge_config
from elenchos.models import Result, Run, judge_generation_params, parse_model_id
from elenchos.providers.registry import get_provider
from elenchos.scoring.judge import (
    JudgeContext,
    JudgeProviderError,
    judge_rubric,
    pairwise_winner,
)
from elenchos.console import console
from elenchos.storage import find_run, load_results, save_comparison

logger = logging.getLogger(__name__)

CompareEventCallback = Callable[[str, dict[str, Any]], None] | None


def _compare_note(message: str) -> None:
    """User-visible compare progress on stderr (works from web worker threads)."""
    logger.info(message)
    console.print(f"[bold cyan]compare[/bold cyan] {message}", highlight=False)


def _log_compare_event(event: str, data: dict[str, Any]) -> None:
    if event == "compare_started":
        _compare_note(
            f"started id={data['comparison_id']} tasks={data['task_count']}"
        )
        return
    if event == "judge_call":
        _compare_note(
            f"task {data['index']}/{data['total']} {data['task_id']} "
            f"judging {data['run_id']} ({data['model']})"
        )
        return
    if event == "score_done":
        _compare_note(
            f"task {data['index']}/{data['total']} {data['task_id']} "
            f"{data['run_id']} -> {data['score']:.2f}"
        )
        return
    if event == "task_done":
        if "scores" in data:
            parts = ", ".join(
                f"{run_id}={score:.2f}"
                for run_id, score in sorted(data["scores"].items())
            )
            winner = data.get("winner_run_id") or "tie"
            _compare_note(
                f"task {data['index']}/{data['total']} {data['task_id']} "
                f"done winner={winner} scores=[{parts}]"
            )
        else:
            winner = data.get("winner_run_id") or "tie"
            _compare_note(
                f"task {data['index']}/{data['total']} {data['task_id']} "
                f"done winner={winner}"
            )
        return
    if event == "compare_finished":
        _compare_note(
            f"finished id={data['comparison_id']} summary={data['summary']}"
        )


def _emit_event(
    callback: CompareEventCallback,
    event: str,
    data: dict[str, Any],
) -> None:
    _log_compare_event(event, data)
    if callback is not None:
        callback(event, data)


class CompareError(ValueError):
    """Run comparison cannot proceed."""


@dataclass
class TaskComparison:
    task_id: str
    prompt: str | None
    winner_run_id: str | None
    rationale: str | None = None
    scores: dict[str, float] = field(default_factory=dict)


@dataclass
class ComparisonArtifact:
    comparison_id: str
    mode: str
    judge_model: str
    benchmark_id: str
    started_at: str
    finished_at: str | None = None
    runs: list[dict] = field(default_factory=list)
    tasks: list[TaskComparison] = field(default_factory=list)
    summary: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "comparison_id": self.comparison_id,
            "mode": self.mode,
            "judge_model": self.judge_model,
            "benchmark_id": self.benchmark_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "runs": self.runs,
            "tasks": [
                {
                    "task_id": task.task_id,
                    "prompt": task.prompt,
                    "winner_run_id": task.winner_run_id,
                    "rationale": task.rationale,
                    "scores": task.scores,
                }
                for task in self.tasks
            ],
            "summary": self.summary,
        }


def _build_judge_context(
    judge_model: str,
    *,
    settings: ElenchosSettings | None = None,
    reasoning_effort: str | None = None,
) -> JudgeContext:
    model_id = parse_model_id(judge_model)
    provider = get_provider(model_id.provider, settings=settings)
    defaults = BUILTIN_PROVIDERS.get(model_id.provider)
    if defaults and defaults.api_key_env and not provider.api_key:
        env_name = defaults.api_key_env
        raise CompareError(
            f"Judge provider {provider.name!r} requires an API key. "
            f"Set {env_name} or ELENCHOS_{provider.name.upper()}_API_KEY."
        )
    if not provider.health_check():
        raise CompareError(
            f"Judge provider {provider.name!r} is unhealthy at {provider.base_url}."
        )
    _compare_note(
        f"judge ready model={model_id.qualified} provider={provider.name} "
        f"endpoint={provider.base_url}"
    )
    return JudgeContext(
        provider=provider,
        model=model_id.model,
        qualified=model_id.qualified,
        params=judge_generation_params(reasoning_effort=reasoning_effort),
    )


def load_runs_for_compare(
    run_ids: list[str],
    *,
    settings: ElenchosSettings | None = None,
) -> list[tuple[Path, Run, list[Result]]]:
    if len(run_ids) < 2:
        raise CompareError("compare requires at least two run ids")

    entries: list[tuple[Path, Run, list[Result]]] = []
    for run_id in run_ids:
        found = find_run(run_id, settings)
        if found is None:
            raise CompareError(f"Run not found: {run_id}")
        run_dir, run = found
        results = load_results(run_dir)
        if not results:
            raise CompareError(f"Run {run_id} has no results")
        entries.append((run_dir, run, results))

    benchmark_ids = {
        entry[1].benchmark.id
        for entry in entries
        if entry[1].benchmark is not None
    }
    if len(benchmark_ids) != 1:
        raise CompareError(
            "All runs must share the same benchmark "
            f"(found: {sorted(benchmark_ids) or ['none']})."
        )

    return entries


def _results_by_task(results: list[Result]) -> dict[str, Result]:
    return {result.task_id: result for result in results}


def _shared_task_ids(
    entries: list[tuple[Path, Run, list[Result]]],
) -> list[str]:
    task_sets = [
        {
            task_id
            for task_id, result in _results_by_task(results).items()
            if not result.error and (result.output or result.output_ref)
        }
        for _, _, results in entries
    ]
    if not task_sets:
        return []
    shared = set.intersection(*task_sets)
    return sorted(shared)


def _output_text(result: Result) -> str:
    return result.output or ""


def compare_runs(
    run_ids: list[str],
    *,
    mode: str | None = None,
    judge_model: str | None = None,
    judge_effort: str | None = None,
    settings: ElenchosSettings | None = None,
    persist: bool = True,
    on_event: CompareEventCallback = None,
) -> tuple[ComparisonArtifact, Path | None]:
    """Compare runs with a judge model; optionally persist artifact."""
    settings = settings or ElenchosSettings()
    try:
        judge_config = resolve_judge_config(
            settings=settings,
            cli_judge=judge_model,
            cli_mode=mode,
        )
    except ValueError as exc:
        raise CompareError(str(exc)) from exc
    if not judge_config.model:
        raise CompareError(
            "No judge model configured. Pass --judge or set judge.model in "
            f"{settings.data_dir / 'config.yaml'}."
        )

    entries = load_runs_for_compare(run_ids, settings=settings)
    benchmark_id = entries[0][1].benchmark.id  # type: ignore[union-attr]
    judge = _build_judge_context(
        judge_config.model,
        settings=settings,
        reasoning_effort=judge_effort,
    )
    compare_mode = judge_config.mode

    started = datetime.now(UTC).isoformat()
    comparison_id = secrets.token_hex(3)
    artifact = ComparisonArtifact(
        comparison_id=comparison_id,
        mode=compare_mode,
        judge_model=judge.qualified,
        benchmark_id=benchmark_id,
        started_at=started,
        runs=[
            {"run_id": run.run_id, "model": run.model}
            for _, run, _ in entries
        ],
    )

    shared_tasks = _shared_task_ids(entries)
    if not shared_tasks:
        raise CompareError("No shared successful tasks across the selected runs")

    _compare_note(
        f"mode={compare_mode} benchmark={benchmark_id} judge={judge.qualified} "
        f"runs={[run.run_id for _, run, _ in entries]}"
    )

    _emit_event(
        on_event,
        "compare_started",
        {"comparison_id": comparison_id, "task_count": len(shared_tasks)},
    )

    if compare_mode == "pairwise":
        artifact.tasks, artifact.summary = _compare_pairwise(
            entries,
            shared_tasks,
            judge=judge,
            on_event=on_event,
        )
    elif compare_mode == "rubric":
        artifact.tasks, artifact.summary = _compare_rubric(
            entries,
            shared_tasks,
            judge=judge,
            on_event=on_event,
        )
    else:
        raise CompareError(f"Unknown compare mode: {compare_mode!r}")

    artifact.finished_at = datetime.now(UTC).isoformat()

    out_path = None
    if persist:
        out_path = save_comparison(artifact, settings=settings)

    _emit_event(
        on_event,
        "compare_finished",
        {
            "comparison_id": artifact.comparison_id,
            "summary": artifact.summary,
        },
    )

    return artifact, out_path


def _compare_pairwise(
    entries: list[tuple[Path, Run, list[Result]]],
    task_ids: list[str],
    *,
    judge: JudgeContext,
    on_event: CompareEventCallback = None,
) -> tuple[list[TaskComparison], dict]:
    if len(entries) != 2:
        raise CompareError(
            "pairwise mode supports exactly two runs; use rubric mode for more."
        )

    (_, run_a, results_a), (_, run_b, results_b) = entries
    by_a = _results_by_task(results_a)
    by_b = _results_by_task(results_b)

    tasks: list[TaskComparison] = []
    wins_a = 0
    wins_b = 0
    ties = 0

    for index, task_id in enumerate(task_ids, start=1):
        result_a = by_a[task_id]
        result_b = by_b[task_id]
        prompt = result_a.prompt or result_b.prompt
        _emit_event(
            on_event,
            "judge_call",
            {
                "task_id": task_id,
                "index": index,
                "total": len(task_ids),
                "run_id": f"{run_a.run_id} vs {run_b.run_id}",
                "model": f"{run_a.model} vs {run_b.model}",
            },
        )
        winner_label, rationale = pairwise_winner(
            judge,
            prompt=prompt or "",
            output_a=_output_text(result_a),
            output_b=_output_text(result_b),
            strict=True,
            context=f"task={task_id}",
        )

        if winner_label == "A":
            winner_run_id = run_a.run_id
            wins_a += 1
        elif winner_label == "B":
            winner_run_id = run_b.run_id
            wins_b += 1
        else:
            winner_run_id = None
            ties += 1

        tasks.append(
            TaskComparison(
                task_id=task_id,
                prompt=prompt,
                winner_run_id=winner_run_id,
                rationale=rationale,
            )
        )
        _emit_event(
            on_event,
            "task_done",
            {
                "task_id": task_id,
                "index": index,
                "total": len(task_ids),
                "winner_run_id": winner_run_id,
            },
        )

    comparable = len(tasks)
    summary = {
        "task_count": comparable,
        "wins": {run_a.run_id: wins_a, run_b.run_id: wins_b},
        "ties": ties,
        "win_rate": {
            run_a.run_id: wins_a / comparable if comparable else 0.0,
            run_b.run_id: wins_b / comparable if comparable else 0.0,
        },
    }
    return tasks, summary


def _compare_rubric(
    entries: list[tuple[Path, Run, list[Result]]],
    task_ids: list[str],
    *,
    judge: JudgeContext,
    on_event: CompareEventCallback = None,
) -> tuple[list[TaskComparison], dict]:
    from elenchos.benchmarks.registry import resolve_benchmark

    benchmark_id = entries[0][1].benchmark.id  # type: ignore[union-attr]
    suite = resolve_benchmark(benchmark_id)

    tasks: list[TaskComparison] = []
    mean_scores: dict[str, list[float]] = {
        entry[1].run_id: [] for entry in entries
    }

    for index, task_id in enumerate(task_ids, start=1):
        suite_task = next((task for task in suite.tasks if task.id == task_id), None)
        rubric_scorer = None
        if suite_task:
            for scorer in suite.effective_scoring(suite_task):
                if scorer.type == "judge_rubric":
                    rubric_scorer = scorer
                    break

        rubric = (
            rubric_scorer.rubric
            if rubric_scorer
            else "Score quality from 1 (poor) to 5 (excellent)."
        )
        if rubric_scorer is None and index == 1:
            _compare_note(
                "benchmark has no judge_rubric scorer; using generic quality rubric"
            )

        scores: dict[str, float] = {}
        best_run_id: str | None = None
        best_score = -1.0

        for _, run, results in entries:
            result = _results_by_task(results)[task_id]
            prompt = result.prompt or (suite_task.prompt if suite_task else "")
            score_context = f"task={task_id} run={run.run_id}"
            _emit_event(
                on_event,
                "judge_call",
                {
                    "task_id": task_id,
                    "index": index,
                    "total": len(task_ids),
                    "run_id": run.run_id,
                    "model": run.model,
                },
            )
            try:
                outcome = judge_rubric(
                    judge,
                    prompt=prompt,
                    output=_output_text(result),
                    rubric=rubric,
                    strict=True,
                    context=score_context,
                )
            except JudgeProviderError as exc:
                raise CompareError(str(exc)) from exc
            score = outcome.score or 0.0
            scores[run.run_id] = score
            mean_scores[run.run_id].append(score)
            _emit_event(
                on_event,
                "score_done",
                {
                    "task_id": task_id,
                    "index": index,
                    "total": len(task_ids),
                    "run_id": run.run_id,
                    "score": score,
                },
            )
            if score > best_score:
                best_score = score
                best_run_id = run.run_id
            elif score == best_score:
                best_run_id = None

        first_result = _results_by_task(entries[0][2])[task_id]
        tasks.append(
            TaskComparison(
                task_id=task_id,
                prompt=first_result.prompt,
                winner_run_id=best_run_id,
                scores=scores,
            )
        )
        _emit_event(
            on_event,
            "task_done",
            {
                "task_id": task_id,
                "index": index,
                "total": len(task_ids),
                "winner_run_id": best_run_id,
                "scores": scores,
            },
        )

    summary = {
        "task_count": len(tasks),
        "mean_score": {
            run_id: (sum(values) / len(values) if values else None)
            for run_id, values in mean_scores.items()
        },
    }
    return tasks, summary
