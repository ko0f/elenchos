import logging
from pathlib import Path
from typing import Annotated

import typer
from rich.panel import Panel
from rich.table import Table

from elenchos import __version__
from elenchos.console import console, setup_logging
from elenchos.models import (
    Result,
    build_messages,
    default_generation_params,
    generation_params_to_dict,
    parse_model_id,
)
from elenchos.providers import get_provider, list_provider_names
from elenchos.runner import run_benchmark
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
app.add_typer(providers_app, name="providers")


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
    if completion.prompt_tokens is not None:
        metrics.add_row("Prompt tokens", str(completion.prompt_tokens))
    if completion.completion_tokens is not None:
        metrics.add_row("Completion tokens", str(completion.completion_tokens))
    if completion.finish_reason:
        metrics.add_row("Finish reason", completion.finish_reason)

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
        if result.prompt_tokens is not None:
            detail.add_row("Prompt tokens", str(result.prompt_tokens))
        if result.completion_tokens is not None:
            detail.add_row("Completion tokens", str(result.completion_tokens))
        if result.finish_reason:
            detail.add_row("Finish reason", result.finish_reason)
        if result.score is not None:
            detail.add_row("Score", f"{result.score:.2f}")
        console.print(detail)


@app.command()
def run(
    prompts: Path = typer.Option(
        Path("prompts/sample.jsonl"),
        "--prompts",
        help="Path to JSONL prompt file",
    ),
) -> None:
    """Run prompts against LM Studio (legacy)."""
    run_benchmark(prompts)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
