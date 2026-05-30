import logging
from pathlib import Path
from typing import Annotated

import typer
from rich.panel import Panel
from rich.table import Table

from elenchos import __version__
from elenchos.benchmarks import (
    BenchmarkNotFoundError,
    format_suite_error,
    list_suite_summaries,
    resolve_benchmark,
)
from elenchos.benchmarks.schema import SuiteValidationError
from elenchos.console import console, setup_logging
from elenchos.models import (
    Result,
    build_messages,
    default_generation_params,
    generation_params_to_dict,
    parse_model_id,
)
from elenchos.providers import get_provider, list_provider_names
from elenchos.reporter import render_run_report
from elenchos.runner import SuiteRunError, run_suite
from elenchos.storage import (
    DEFAULT_TASK_ID,
    append_result,
    create_run,
    finalize_run,
    find_run,
    list_runs,
    load_results,
    save_output,
)

logger = logging.getLogger(__name__)

app = typer.Typer(no_args_is_help=True)
providers_app = typer.Typer(no_args_is_help=True)
bench_app = typer.Typer(no_args_is_help=True)
app.add_typer(providers_app, name="providers")
app.add_typer(bench_app, name="bench")


def _add_token_rows(
    table: Table,
    *,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    finish_reason: str | None,
) -> None:
    if prompt_tokens is not None:
        table.add_row("Prompt tokens", str(prompt_tokens))
    if completion_tokens is not None:
        table.add_row("Completion tokens", str(completion_tokens))
    if finish_reason:
        table.add_row("Finish reason", finish_reason)


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    setup_logging(level)


@app.callback()
def main_callback(
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Enable debug logging on stderr"),
    ] = False,
) -> None:
    _configure_logging(verbose)


@app.command()
def version() -> None:
    """Print the installed version."""
    console.print(__version__)


@providers_app.command("list")
def providers_list() -> None:
    """List configured providers and health status."""
    table = Table(title="Providers")
    table.add_column("Provider")
    table.add_column("Endpoint")
    table.add_column("Status")

    for name in list_provider_names():
        provider = get_provider(name)
        healthy = provider.health_check()
        status = "[green]healthy[/green]" if healthy else "[red]unhealthy[/red]"
        table.add_row(name, provider.base_url, status)

    console.print(table)


@bench_app.command("list")
def bench_list() -> None:
    """List available benchmark suites."""
    summaries = list_suite_summaries()
    if not summaries:
        console.print("[dim]No benchmark suites found.[/dim]")
        return

    table = Table(title="Benchmark Suites")
    table.add_column("ID")
    table.add_column("Version")
    table.add_column("Type")
    table.add_column("Tasks")
    table.add_column("Source")
    table.add_column("Description")

    for summary in summaries:
        table.add_row(
            summary.id,
            str(summary.version),
            summary.type,
            str(summary.task_count),
            summary.source,
            summary.description,
        )

    console.print(table)


@bench_app.command("show")
def bench_show(
    benchmark_ref: Annotated[
        str,
        typer.Argument(help="Suite id or path to a .yaml file"),
    ],
    benchmark_file: Annotated[
        Path | None,
        typer.Option(
            "--benchmark-file",
            help="Load a suite from this YAML file instead of the registry",
        ),
    ] = None,
) -> None:
    """Show tasks in a benchmark suite."""
    try:
        suite = resolve_benchmark(
            benchmark_ref,
            benchmark_file=benchmark_file,
        )
    except (BenchmarkNotFoundError, SuiteValidationError) as exc:
        console.print(f"[red]{format_suite_error(exc)}[/red]")
        raise typer.Exit(code=1) from exc

    meta = Table(show_header=False, box=None, padding=(0, 1))
    meta.add_row("ID", suite.id)
    meta.add_row("Version", str(suite.version))
    meta.add_row("Type", suite.type)
    if suite.description:
        meta.add_row("Description", suite.description)
    meta.add_row("Tasks", str(len(suite.tasks)))
    console.print(Panel(meta, title="Benchmark", expand=False))

    for task in suite.tasks:
        task_type = suite.effective_task_type(task)
        scorers = suite.effective_scoring(task)
        scorer_names = ", ".join(scorer.type for scorer in scorers) or "—"

        header = Table(show_header=False, box=None, padding=(0, 1))
        header.add_row("Type", task_type)
        header.add_row("Scoring", scorer_names)
        console.print(Panel(header, title=task.id, expand=False))
        console.print(
            Panel(task.prompt.rstrip(), title=f"{task.id} — prompt", expand=False)
        )


@app.command()
def prompt(
    text: Annotated[str, typer.Argument(help="Prompt text to send to the model")],
    model: Annotated[str, typer.Option("--model", help="Model id: provider/model")],
) -> None:
    """Send a single prompt to a model and print the response."""
    model_id = parse_model_id(model)
    provider = get_provider(model_id.provider)
    messages = build_messages(text)
    params = default_generation_params()

    logger.info(
        "Sending prompt to %s via %s",
        model_id.qualified,
        provider.name,
    )

    if not provider.health_check():
        console.print(
            f"[red]Provider {provider.name!r} is unhealthy at {provider.base_url}. "
            "Check ELENCHOS_OLLAMA_BASE_URL or ~/.elenchos/config.yaml.[/red]"
        )
        raise typer.Exit(code=1)

    run_dir, run = create_run(
        model=model_id.qualified,
        params=generation_params_to_dict(params),
    )

    try:
        completion = provider.complete(model_id.model, messages, params)
    except Exception as exc:
        logger.exception("Completion failed")
        result = Result(
            task_id=DEFAULT_TASK_ID,
            prompt=text,
            latency_ms=0.0,
            error=str(exc),
        )
        append_result(run_dir, result)
        finalize_run(run_dir, run)
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    output_ref = save_output(run_dir, DEFAULT_TASK_ID, completion.text)
    append_result(
        run_dir,
        Result(
            task_id=DEFAULT_TASK_ID,
            prompt=text,
            latency_ms=completion.latency_ms,
            prompt_tokens=completion.prompt_tokens,
            completion_tokens=completion.completion_tokens,
            output_ref=output_ref,
            finish_reason=completion.finish_reason,
        ),
    )
    finalize_run(run_dir, run)

    console.print(Panel(completion.text, title=model_id.qualified, expand=False))

    metrics = Table(show_header=False, box=None, padding=(0, 1))
    metrics.add_row("Run ID", run.run_id)
    metrics.add_row("Latency", f"{completion.latency_ms:.0f} ms")
    _add_token_rows(
        metrics,
        prompt_tokens=completion.prompt_tokens,
        completion_tokens=completion.completion_tokens,
        finish_reason=completion.finish_reason,
    )

    console.print(metrics)


@app.command("list")
def list_runs_cmd() -> None:
    """List persisted runs."""
    runs = list_runs()
    if not runs:
        console.print("[dim]No runs yet. Try:[/dim] elenchos prompt --model ollama/…")
        return

    table = Table(title="Runs")
    table.add_column("Run ID")
    table.add_column("Started")
    table.add_column("Benchmark")
    table.add_column("Model")

    for run in runs:
        bench = run.benchmark.id if run.benchmark else "—"
        table.add_row(run.run_id, run.started_at, bench, run.model)

    console.print(table)


@app.command()
def show(
    run_id: Annotated[str, typer.Argument(help="Run id from elenchos list")],
) -> None:
    """Show details for a persisted run."""
    found = find_run(run_id)
    if found is None:
        console.print(f"[red]Run not found:[/red] {run_id}")
        raise typer.Exit(code=1)

    run_dir, run = found
    results = load_results(run_dir)
    if not results:
        console.print(f"[red]Run {run_id} has no results.[/red]")
        raise typer.Exit(code=1)

    meta = Table(show_header=False, box=None, padding=(0, 1))
    meta.add_row("Run ID", run.run_id)
    meta.add_row("Model", run.model)
    if run.benchmark:
        meta.add_row("Benchmark", run.benchmark.id)
    meta.add_row("Started", run.started_at)
    if run.finished_at:
        meta.add_row("Finished", run.finished_at)
    if run.summary:
        mean_score = run.summary.get("mean_score")
        if mean_score is not None:
            meta.add_row("Mean score", f"{mean_score:.2f}")
        pass_rate = run.summary.get("pass_rate")
        if pass_rate is not None:
            meta.add_row("Pass rate", f"{pass_rate * 100:.0f}%")
        p95 = run.summary.get("p95_latency_ms")
        if p95 is not None:
            meta.add_row("P95 latency", f"{p95:.0f} ms")
    console.print(Panel(meta, title="Run", expand=False))

    for result in results:
        title = result.task_id
        if result.error:
            console.print(
                Panel(f"[red]{result.error}[/red]", title=title, expand=False)
            )
            continue

        if result.prompt:
            console.print(Panel(result.prompt, title=f"{title} — prompt", expand=False))
        if result.output:
            console.print(Panel(result.output, title=f"{title} — output", expand=False))

        detail = Table(show_header=False, box=None, padding=(0, 1))
        detail.add_row("Latency", f"{result.latency_ms:.0f} ms")
        _add_token_rows(
            detail,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            finish_reason=result.finish_reason,
        )
        if result.score is not None:
            detail.add_row("Score", f"{result.score:.2f}")
        console.print(detail)


@app.command()
def run(
    benchmark: Annotated[
        str,
        typer.Option("--benchmark", help="Benchmark suite id"),
    ],
    model: Annotated[
        str,
        typer.Option("--model", help="Model id: provider/model"),
    ],
    benchmark_file: Annotated[
        Path | None,
        typer.Option(
            "--benchmark-file",
            help="Load benchmark from this YAML file instead of the registry",
        ),
    ] = None,
    temperature: Annotated[
        float | None,
        typer.Option("--temperature", help="Override suite default temperature"),
    ] = None,
    max_tokens: Annotated[
        int | None,
        typer.Option("--max-tokens", help="Override suite default max tokens"),
    ] = None,
    allow_code_exec: Annotated[
        bool,
        typer.Option(
            "--allow-code-exec",
            help="Allow sandboxed execution of model-generated code (unit_test scorer)",
        ),
    ] = False,
) -> None:
    """Run a benchmark suite against a model."""
    try:
        suite = resolve_benchmark(
            benchmark,
            benchmark_file=benchmark_file,
        )
    except (BenchmarkNotFoundError, SuiteValidationError) as exc:
        console.print(f"[red]{format_suite_error(exc)}[/red]")
        raise typer.Exit(code=1) from exc

    try:
        outcome = run_suite(
            suite,
            model,
            temperature=temperature,
            max_tokens=max_tokens,
            allow_code_exec=allow_code_exec,
        )
    except SuiteRunError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    render_run_report(outcome.run, outcome.results, outcome.summary)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
