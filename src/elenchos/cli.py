import argparse
from pathlib import Path

from elenchos.runner import run_benchmark


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="elenchos")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run prompts against LM Studio")
    run_parser.add_argument(
        "--prompts",
        type=Path,
        default=Path("prompts/sample.jsonl"),
        help="Path to JSONL prompt file",
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "run":
        run_benchmark(args.prompts)
