import logging
from pathlib import Path
from typing import Annotated

import typer
from rich.panel import Panel
from rich.table import Table

from elenchos import __version__
from elenchos.console import console, setup_logging
from elenchos.models import build_messages, default_generation_params, parse_model_id
from elenchos.providers import get_provider, list_provider_names
from elenchos.runner import run_benchmark

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

    try:
        completion = provider.complete(model_id.model, messages, params)
    except Exception as exc:
        logger.exception("Completion failed")
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(Panel(completion.text, title=model_id.qualified, expand=False))

    metrics = Table(show_header=False, box=None, padding=(0, 1))
    metrics.add_row("Latency", f"{completion.latency_ms:.0f} ms")
    if completion.prompt_tokens is not None:
        metrics.add_row("Prompt tokens", str(completion.prompt_tokens))
    if completion.completion_tokens is not None:
        metrics.add_row("Completion tokens", str(completion.completion_tokens))
    if completion.finish_reason:
        metrics.add_row("Finish reason", completion.finish_reason)

    console.print(metrics)


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
