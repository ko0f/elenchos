"""Shared Rich console and logging setup."""

import logging

from rich.console import Console
from rich.logging import RichHandler

console = Console()
_log_stderr = Console(stderr=True)


def setup_logging(level: int = logging.INFO) -> None:
    """Configure stderr logging with RichHandler and level-based color."""
    root = logging.getLogger()
    if root.handlers:
        root.setLevel(level)
        for handler in root.handlers:
            handler.setLevel(level)
        return

    handler = RichHandler(
        console=_log_stderr,
        rich_tracebacks=True,
        show_time=True,
        show_path=False,
    )
    handler.setLevel(level)
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[handler],
    )
