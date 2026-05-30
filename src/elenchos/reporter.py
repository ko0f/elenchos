"""Render benchmark run results and multi-run reports."""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass

from rich.table import Table

from elenchos.console import console
from elenchos.metrics import aggregate_run_summary
from elenchos.models import Result, Run
from elenchos.storage import list_runs, load_results, runs_root


class ReportError(ValueError):
    """Report cannot be generated."""


@dataclass
class LeaderboardRow:
    run_id: str
    model: str
    benchmark_id: str | None
    mean_score: float | None
    pass_rate: float | None
    p95_latency_ms: float | None
    task_count: int | None
    rank: int | None = None
    win_rate: float | None = None


@dataclass
class LeaderboardReport:
    benchmark_id: str | None
    rows: list[LeaderboardRow]

    @property
    def has_win_rate(self) -> bool:
        return any(row.win_rate is not None for row in self.rows)

    def to_dict(self) -> dict:
        return {
            "benchmark_id": self.benchmark_id,
            "runs": [
                {
                    "run_id": row.run_id,
                    "model": row.model,
                    "benchmark_id": row.benchmark_id,
                    "mean_score": row.mean_score,
                    "pass_rate": row.pass_rate,
                    "p95_latency_ms": row.p95_latency_ms,
                    "task_count": row.task_count,
                    "rank": row.rank,
                    "win_rate": row.win_rate,
                }
                for row in self.rows
            ],
        }


def build_leaderboard(
    run_ids: list[str],
    *,
    win_rates: dict[str, float] | None = None,
) -> LeaderboardReport:
    if not run_ids:
        raise ReportError("report requires at least one run id")

    rows: list[LeaderboardRow] = []
    benchmark_ids: set[str | None] = set()

    root = runs_root()
    runs_by_id = {run.run_id: run for run in list_runs()}
    for run_id in run_ids:
        run = runs_by_id.get(run_id)
        if run is None or run.dir_name is None:
            raise ReportError(f"Run not found: {run_id}")
        run_dir = root / run.dir_name
        results = load_results(run_dir, include_output=False)
        summary = run.summary or aggregate_run_summary(results)
        benchmark_id = run.benchmark.id if run.benchmark else None
        benchmark_ids.add(benchmark_id)
        rows.append(
            LeaderboardRow(
                run_id=run.run_id,
                model=run.model,
                benchmark_id=benchmark_id,
                mean_score=summary.get("mean_score"),
                pass_rate=summary.get("pass_rate"),
                p95_latency_ms=summary.get("p95_latency_ms"),
                task_count=summary.get("task_count"),
                win_rate=(win_rates or {}).get(run.run_id),
            )
        )

    if len(benchmark_ids) > 1:
        raise ReportError(
            "All runs must share the same benchmark "
            f"(found: {sorted(benchmark_ids) or ['none']})."
        )

    ranked = sorted(
        rows,
        key=lambda row: (
            row.mean_score is None,
            -(row.mean_score or 0.0),
            row.model,
        ),
    )
    for index, row in enumerate(ranked, start=1):
        if row.mean_score is not None:
            row.rank = index

    return LeaderboardReport(
        benchmark_id=next(iter(benchmark_ids)) if benchmark_ids else None,
        rows=ranked,
    )


def _display_cells(
    row: LeaderboardRow, *, include_run_id: bool, has_win_rate: bool
) -> list[str]:
    """Format a row for human-facing output (Markdown table and Rich table)."""
    cells = [
        str(row.rank) if row.rank is not None else "—",
        row.model,
    ]
    if include_run_id:
        cells.append(row.run_id)
    cells.append(f"{row.mean_score:.2f}" if row.mean_score is not None else "—")
    cells.append(f"{row.pass_rate * 100:.0f}%" if row.pass_rate is not None else "—")
    cells.append(
        f"{row.p95_latency_ms:.0f} ms" if row.p95_latency_ms is not None else "—"
    )
    if has_win_rate:
        cells.append(f"{row.win_rate * 100:.0f}%" if row.win_rate is not None else "—")
    return cells


def format_report_md(report: LeaderboardReport) -> str:
    lines = ["# Benchmark Report", ""]
    if report.benchmark_id:
        lines.append(f"**Benchmark:** {report.benchmark_id}")
        lines.append("")

    has_win_rate = report.has_win_rate
    headers = ["Rank", "Model", "Mean Score", "Pass Rate", "P95 Latency"]
    if has_win_rate:
        headers.append("Win Rate")
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")

    for row in report.rows:
        cells = _display_cells(row, include_run_id=False, has_win_rate=has_win_rate)
        lines.append("| " + " | ".join(cells) + " |")

    return "\n".join(lines) + "\n"


def format_report_csv(report: LeaderboardReport) -> str:
    buffer = io.StringIO()
    fieldnames = [
        "rank",
        "run_id",
        "model",
        "mean_score",
        "pass_rate",
        "p95_latency_ms",
        "task_count",
    ]
    if report.has_win_rate:
        fieldnames.append("win_rate")

    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for row in report.rows:
        payload = {
            "rank": row.rank if row.rank is not None else "",
            "run_id": row.run_id,
            "model": row.model,
            "mean_score": (
                f"{row.mean_score:.4f}" if row.mean_score is not None else ""
            ),
            "pass_rate": (
                f"{row.pass_rate:.4f}" if row.pass_rate is not None else ""
            ),
            "p95_latency_ms": (
                f"{row.p95_latency_ms:.0f}"
                if row.p95_latency_ms is not None
                else ""
            ),
            "task_count": row.task_count if row.task_count is not None else "",
        }
        if "win_rate" in fieldnames:
            payload["win_rate"] = (
                f"{row.win_rate:.4f}" if row.win_rate is not None else ""
            )
        writer.writerow(payload)

    return buffer.getvalue()


def format_report_json(report: LeaderboardReport) -> str:
    return json.dumps(report.to_dict(), indent=2) + "\n"


def format_report(report: LeaderboardReport, fmt: str) -> str:
    normalized = fmt.lower()
    if normalized == "md":
        return format_report_md(report)
    if normalized == "csv":
        return format_report_csv(report)
    if normalized == "json":
        return format_report_json(report)
    raise ReportError(f"Unknown report format {fmt!r}; expected md, csv, or json.")


def render_leaderboard_report(report: LeaderboardReport) -> None:
    title = "Leaderboard"
    if report.benchmark_id:
        title = f"Leaderboard — {report.benchmark_id}"

    table = Table(title=title)
    table.add_column("Rank", justify="right")
    table.add_column("Model")
    table.add_column("Run ID")
    table.add_column("Mean Score", justify="right")
    table.add_column("Pass Rate", justify="right")
    table.add_column("P95 Latency", justify="right")
    has_win_rate = report.has_win_rate
    if has_win_rate:
        table.add_column("Win Rate", justify="right")

    for row in report.rows:
        cells = _display_cells(row, include_run_id=True, has_win_rate=has_win_rate)
        table.add_row(*cells)

    console.print(table)


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
