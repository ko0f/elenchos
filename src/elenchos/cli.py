from pathlib import Path

import typer

from elenchos import __version__
from elenchos.runner import run_benchmark

app = typer.Typer(no_args_is_help=True)


@app.command()
def version() -> None:
    """Print the installed version."""
    typer.echo(__version__)


@app.command()
def run(
    prompts: Path = typer.Option(
        Path("prompts/sample.jsonl"),
        "--prompts",
        help="Path to JSONL prompt file",
    ),
) -> None:
    """Run prompts against LM Studio."""
    run_benchmark(prompts)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
