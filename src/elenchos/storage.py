"""Run/result persistence under ~/.elenchos/runs/."""

from __future__ import annotations

import json
import secrets
from datetime import UTC, datetime
from pathlib import Path

from elenchos import __version__
from elenchos.config import ElenchosSettings
from elenchos.models import BenchmarkRef, Result, Run

DEFAULT_TASK_ID = "prompt"


def _settings(settings: ElenchosSettings | None) -> ElenchosSettings:
    return settings or ElenchosSettings()


def runs_root(settings: ElenchosSettings | None = None, *, create: bool = False) -> Path:
    root = _settings(settings).data_dir / "runs"
    if create:
        root.mkdir(parents=True, exist_ok=True)
    return root


def generate_run_id() -> str:
    return secrets.token_hex(3)


def _timestamp_dir(started_at: datetime) -> str:
    return started_at.strftime("%Y-%m-%dT%H-%M-%S")


def _sanitize_path_component(value: str) -> str:
    return (
        value.replace("/", "_")
        .replace(":", "-")
        .replace(" ", "-")
    )


def _run_dir_name(
    *,
    started_at: datetime,
    benchmark_id: str,
    model: str,
    run_id: str,
) -> str:
    stamp = _timestamp_dir(started_at)
    bench = _sanitize_path_component(benchmark_id)
    model_part = _sanitize_path_component(model)
    return f"{stamp}_{bench}_{model_part}_{run_id}"


def create_run(
    *,
    model: str,
    params: dict,
    benchmark: BenchmarkRef | None = None,
    settings: ElenchosSettings | None = None,
) -> tuple[Path, Run]:
    """Create a timestamped run directory and write initial ``run.json``."""
    started = datetime.now(UTC)
    run_id = generate_run_id()
    bench = benchmark or BenchmarkRef(id="prompt")
    run = Run(
        run_id=run_id,
        started_at=started.isoformat(),
        benchmark=bench,
        model=model,
        params=params,
        tool_version=__version__,
    )
    dir_name = _run_dir_name(
        started_at=started,
        benchmark_id=bench.id,
        model=model,
        run_id=run_id,
    )
    run_dir = runs_root(settings, create=True) / dir_name
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "outputs").mkdir()
    write_run(run_dir, run)
    return run_dir, run


def write_run(run_dir: Path, run: Run) -> None:
    payload = run.to_dict()
    path = run_dir / "run.json"
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")


def finalize_run(run_dir: Path, run: Run) -> None:
    run.finished_at = datetime.now(UTC).isoformat()
    write_run(run_dir, run)


def save_output(run_dir: Path, task_id: str, text: str) -> str:
    rel = f"outputs/{task_id}.txt"
    path = run_dir / rel
    path.write_text(text, encoding="utf-8")
    return rel


def append_result(run_dir: Path, result: Result) -> None:
    path = run_dir / "results.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(result.to_dict(), ensure_ascii=False))
        handle.write("\n")


def read_output(run_dir: Path, output_ref: str) -> str:
    return (run_dir / output_ref).read_text(encoding="utf-8")


def load_results(run_dir: Path, *, include_output: bool = True) -> list[Result]:
    path = run_dir / "results.jsonl"
    if not path.is_file():
        return []

    results: list[Result] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            results.append(Result.from_dict(json.loads(line)))

    if include_output:
        for result in results:
            if result.output_ref and result.output is None:
                result.output = read_output(run_dir, result.output_ref)

    return results


def _read_run_json(path: Path) -> Run:
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    run = Run.from_dict(payload)
    run.dir_name = path.parent.name
    return run


def list_runs(settings: ElenchosSettings | None = None) -> list[Run]:
    root = runs_root(settings)
    if not root.is_dir():
        return []
    runs: list[Run] = []
    for entry in root.iterdir():
        if not entry.is_dir():
            continue
        run_json = entry / "run.json"
        if not run_json.is_file():
            continue
        runs.append(_read_run_json(run_json))

    runs.sort(key=lambda run: run.started_at, reverse=True)
    return runs


def find_run(
    run_id: str,
    settings: ElenchosSettings | None = None,
) -> tuple[Path, Run] | None:
    root = runs_root(settings)
    if not root.is_dir():
        return None
    for entry in root.iterdir():
        if not entry.is_dir():
            continue
        run_json = entry / "run.json"
        if not run_json.is_file():
            continue
        run = _read_run_json(run_json)
        if run.run_id == run_id:
            return entry, run
    return None
