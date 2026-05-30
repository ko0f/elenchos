"""Render benchmark run results to the terminal."""

from __future__ import annotations

from rich.table import Table

from elenchos.console import console
from elenchos.models import Result, Run


def _score_style(score: float | None) -> str:
    if score is None:
        return "dim"
    if score >= 1.0:
        return "green"
    if score > 0:
        return "yellow"
    return "red"


def _format_score(score: float | None) -> str:
    if score is None:
        return "—"
    return f"{score:.2f}"


def _format_status(result: Result) -> str:
    if result.error:
        return "[red]error[/red]"
    if result.score is None:
        return "[dim]unscored[/dim]"
    if result.score >= 1.0:
        return "[green]pass[/green]"
    if result.score > 0:
        return "[yellow]partial[/yellow]"
    return "[red]fail[/red]"


def render_task_results(results: list[Result]) -> None:
    table = Table(title="Task Results")
    table.add_column("Task")
    table.add_column("Score", justify="right")
    table.add_column("Scorer")
    table.add_column("Latency", justify="right")
    table.add_column("Status")

    for result in results:
        style = _score_style(result.score if not result.error else None)
        table.add_row(
            result.task_id,
            f"[{style}]{_format_score(result.score)}[/{style}]",
            result.scorer or "—",
            f"{result.latency_ms:.0f} ms",
            _format_status(result),
        )

    console.print(table)


def render_run_summary(run: Run, summary: dict) -> None:
    table = Table(title="Summary", show_header=False, box=None, padding=(0, 1))
    table.add_row("Run ID", run.run_id)
    table.add_row("Benchmark", run.benchmark.id if run.benchmark else "—")
    table.add_row("Model", run.model)

    mean_score = summary.get("mean_score")
    if mean_score is not None:
        style = _score_style(mean_score)
        table.add_row("Mean score", f"[{style}]{mean_score:.2f}[/{style}]")

    pass_rate = summary.get("pass_rate")
    if pass_rate is not None:
        table.add_row("Pass rate", f"{pass_rate * 100:.0f}%")

    p95 = summary.get("p95_latency_ms")
    if p95 is not None:
        table.add_row("P95 latency", f"{p95:.0f} ms")

    task_count = summary.get("task_count")
    if task_count is not None:
        table.add_row("Tasks", str(task_count))

    errors = summary.get("errors")
    if errors:
        table.add_row("Errors", str(errors))

    console.print(table)


def render_run_report(run: Run, results: list[Result], summary: dict) -> None:
    render_task_results(results)
    render_run_summary(run, summary)


def _run_model_label(artifact, run_id: str) -> str:
    for entry in artifact.runs:
        if entry["run_id"] == run_id:
            return entry["model"]
    return run_id


def render_comparison_report(artifact) -> None:
    """Render a judge comparison artifact to the terminal."""
    from elenchos.compare import ComparisonArtifact

    if not isinstance(artifact, ComparisonArtifact):
        raise TypeError("expected ComparisonArtifact")

    meta = Table(title="Comparison", show_header=False, box=None, padding=(0, 1))
    meta.add_row("Comparison ID", artifact.comparison_id)
    meta.add_row("Mode", artifact.mode)
    meta.add_row("Judge", artifact.judge_model)
    meta.add_row("Benchmark", artifact.benchmark_id)
    for entry in artifact.runs:
        meta.add_row(f"Run {entry['run_id']}", entry["model"])
    console.print(meta)

    table = Table(title="Task Comparisons")
    table.add_column("Task")
    if artifact.mode == "rubric":
        for entry in artifact.runs:
            table.add_column(entry["run_id"], justify="right")
        table.add_column("Winner")
        run_labels = {entry["run_id"]: entry["model"] for entry in artifact.runs}
        for task in artifact.tasks:
            row = [task.task_id]
            for entry in artifact.runs:
                score = task.scores.get(entry["run_id"])
                row.append(_format_score(score))
            if task.winner_run_id:
                winner = run_labels.get(task.winner_run_id, task.winner_run_id)
            else:
                winner = "tie"
            row.append(winner)
            table.add_row(*row)
    else:
        table.add_column("Winner")
        table.add_column("Rationale")
        run_labels = {entry["run_id"]: entry["model"] for entry in artifact.runs}
        for task in artifact.tasks:
            if task.winner_run_id:
                winner = run_labels.get(task.winner_run_id, task.winner_run_id)
            else:
                winner = "tie"
            rationale = (task.rationale or "—")[:80]
            table.add_row(task.task_id, winner, rationale)

    console.print(table)

    summary_table = Table(title="Summary", show_header=False, box=None, padding=(0, 1))
    if artifact.mode == "pairwise":
        win_rate = artifact.summary.get("win_rate", {})
        for run_id, rate in win_rate.items():
            model = _run_model_label(artifact, run_id)
            summary_table.add_row(f"Win rate ({model})", f"{rate * 100:.0f}%")
        ties = artifact.summary.get("ties")
        if ties is not None:
            summary_table.add_row("Ties", str(ties))
    else:
        mean_score = artifact.summary.get("mean_score", {})
        for run_id, score in mean_score.items():
            if score is None:
                continue
            model = _run_model_label(artifact, run_id)
            style = _score_style(score)
            summary_table.add_row(
                f"Mean score ({model})",
                f"[{style}]{score:.2f}[/{style}]",
            )

    console.print(summary_table)
