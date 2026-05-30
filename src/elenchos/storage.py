"""Run/result persistence under ~/.elenchos/runs/."""

from __future__ import annotations

import json
import secrets
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from elenchos import __version__
from elenchos.config import ElenchosSettings, get_settings
from elenchos.models import BenchmarkRef, Result, Run

DEFAULT_TASK_ID = "prompt"


def _settings(settings: ElenchosSettings | None) -> ElenchosSettings:
    return settings or get_settings()


def runs_root(
    settings: ElenchosSettings | None = None,
    *,
    create: bool = False,
) -> Path:
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


def comparisons_root(
    settings: ElenchosSettings | None = None,
    *,
    create: bool = False,
) -> Path:
    root = _settings(settings).data_dir / "comparisons"
    if create:
        root.mkdir(parents=True, exist_ok=True)
    return root


def _comparison_dir_name(*, started_at: datetime, mode: str, comparison_id: str) -> str:
    stamp = _timestamp_dir(started_at)
    mode_part = _sanitize_path_component(mode)
    return f"{stamp}_{mode_part}_{comparison_id}"


def _read_comparison_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def list_comparisons(
    settings: ElenchosSettings | None = None,
) -> list[dict]:
    """Return comparison summaries newest-first from ~/.elenchos/comparisons/."""
    root = comparisons_root(settings)
    if not root.is_dir():
        return []

    summaries: list[dict] = []
    for entry in root.iterdir():
        if not entry.is_dir():
            continue
        path = entry / "comparison.json"
        if not path.is_file():
            continue
        payload = _read_comparison_json(path)
        summaries.append(
            {
                "comparison_id": payload.get("comparison_id"),
                "mode": payload.get("mode"),
                "judge_model": payload.get("judge_model"),
                "benchmark_id": payload.get("benchmark_id"),
                "started_at": payload.get("started_at"),
                "finished_at": payload.get("finished_at"),
                "run_ids": [
                    item.get("run_id")
                    for item in payload.get("runs", [])
                    if item.get("run_id")
                ],
                "summary": payload.get("summary"),
            }
        )

    summaries.sort(key=lambda item: item.get("started_at") or "", reverse=True)
    return summaries


def find_comparison(
    comparison_id: str,
    settings: ElenchosSettings | None = None,
) -> tuple[Path, dict] | None:
    root = comparisons_root(settings)
    if not root.is_dir():
        return None
    for entry in root.iterdir():
        if not entry.is_dir():
            continue
        path = entry / "comparison.json"
        if not path.is_file():
            continue
        payload = _read_comparison_json(path)
        if payload.get("comparison_id") == comparison_id:
            return entry, payload
    return None


def save_comparison(
    artifact,
    *,
    settings: ElenchosSettings | None = None,
) -> Path:
    """Persist a comparison artifact under ~/.elenchos/comparisons/."""
    started = datetime.fromisoformat(artifact.started_at.replace("Z", "+00:00"))
    dir_name = _comparison_dir_name(
        started_at=started,
        mode=artifact.mode,
        comparison_id=artifact.comparison_id,
    )
    comp_dir = comparisons_root(settings, create=True) / dir_name
    comp_dir.mkdir(parents=True, exist_ok=False)
    path = comp_dir / "comparison.json"
    with path.open("w", encoding="utf-8") as handle:
        json.dump(artifact.to_dict(), handle, indent=2)
        handle.write("\n")
    return comp_dir


def rewrite_results(run_dir: Path, results: list[Result]) -> None:
    """Atomically rewrite ``results.jsonl`` to contain exactly ``results``."""
    path = run_dir / "results.jsonl"
    tmp = path.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        for result in results:
            handle.write(json.dumps(result.to_dict(), ensure_ascii=False))
            handle.write("\n")
    tmp.replace(path)


def find_resumable_run(
    benchmark_id: str,
    model: str,
    *,
    version: int | None = None,
    params: dict | None = None,
    settings: ElenchosSettings | None = None,
) -> tuple[Path, Run] | None:
    """Find the most recent incomplete run matching benchmark/model/version/params."""
    root = runs_root(settings)
    for run in list_runs(settings):
        if run.finished_at is not None:
            continue
        if run.benchmark is None or run.benchmark.id != benchmark_id:
            continue
        if version is not None and run.benchmark.version != version:
            continue
        if run.model != model:
            continue
        if params is not None and run.params != params:
            continue
        if run.dir_name is not None:
            return root / run.dir_name, run
    return None


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


def _baselines_path(settings: ElenchosSettings | None = None) -> Path:
    return _settings(settings).data_dir / "baselines.json"


@dataclass(frozen=True)
class BaselineEntry:
    run_id: str
    comparison_id: str | None = None


def _parse_baseline_entry(value: object) -> BaselineEntry | None:
    if isinstance(value, str):
        return BaselineEntry(run_id=value)
    if isinstance(value, dict):
        run_id = value.get("run_id")
        if not run_id:
            return None
        comparison_id = value.get("comparison_id")
        return BaselineEntry(
            run_id=str(run_id),
            comparison_id=str(comparison_id) if comparison_id else None,
        )
    return None


def load_baseline_entries(
    settings: ElenchosSettings | None = None,
) -> dict[str, BaselineEntry]:
    path = _baselines_path(settings)
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        return {}

    entries: dict[str, BaselineEntry] = {}
    for benchmark_id, value in payload.items():
        entry = _parse_baseline_entry(value)
        if entry is not None:
            entries[str(benchmark_id)] = entry
    return entries


def load_baselines(settings: ElenchosSettings | None = None) -> dict[str, str]:
    return {
        benchmark_id: entry.run_id
        for benchmark_id, entry in load_baseline_entries(settings).items()
    }


def get_baseline_entry(
    benchmark_id: str,
    settings: ElenchosSettings | None = None,
) -> BaselineEntry | None:
    return load_baseline_entries(settings).get(benchmark_id)


def get_baseline_run_id(
    benchmark_id: str,
    settings: ElenchosSettings | None = None,
) -> str | None:
    entry = get_baseline_entry(benchmark_id, settings)
    return entry.run_id if entry is not None else None


def get_baseline_comparison_id(
    benchmark_id: str,
    settings: ElenchosSettings | None = None,
) -> str | None:
    entry = get_baseline_entry(benchmark_id, settings)
    return entry.comparison_id if entry is not None else None


def _write_baselines(
    baselines: dict[str, str],
    settings: ElenchosSettings | None = None,
) -> None:
    _write_baselines_raw(baselines, settings)


def set_baseline(
    benchmark_id: str,
    run_id: str,
    settings: ElenchosSettings | None = None,
) -> None:
    """Set the baseline run for a benchmark. Raises ValueError if run is invalid."""
    found = find_run(run_id, settings)
    if found is None:
        raise ValueError(f"Run not found: {run_id}")
    _run_dir, run = found
    if run.benchmark is None or run.benchmark.id != benchmark_id:
        raise ValueError(
            f"Run {run_id!r} benchmark {run.benchmark!r} does not match {benchmark_id!r}"
        )
    entries = load_baseline_entries(settings)
    previous = entries.get(benchmark_id)
    entries[benchmark_id] = BaselineEntry(
        run_id=run_id,
        comparison_id=previous.comparison_id if previous else None,
    )
    _write_baseline_entries(entries, settings)


def set_baseline_comparison(
    benchmark_id: str,
    comparison_id: str,
    settings: ElenchosSettings | None = None,
) -> None:
    """Pin a rubric comparison as the vs-baseline score source for a benchmark."""
    entry = get_baseline_entry(benchmark_id, settings)
    if entry is None:
        raise ValueError(f"No baseline set for benchmark {benchmark_id!r}")
    entries = load_baseline_entries(settings)
    entries[benchmark_id] = BaselineEntry(
        run_id=entry.run_id,
        comparison_id=comparison_id,
    )
    _write_baseline_entries(entries, settings)


def clear_baseline_comparison(
    benchmark_id: str,
    settings: ElenchosSettings | None = None,
) -> None:
    """Stop using a pinned comparison for vs-baseline scores."""
    entry = get_baseline_entry(benchmark_id, settings)
    if entry is None or not entry.comparison_id:
        return
    entries = load_baseline_entries(settings)
    entries[benchmark_id] = BaselineEntry(
        run_id=entry.run_id,
        comparison_id=None,
    )
    _write_baseline_entries(entries, settings)


def _write_baseline_entries(
    entries: dict[str, BaselineEntry],
    settings: ElenchosSettings | None = None,
) -> None:
    payload: dict[str, dict[str, str] | str] = {}
    for benchmark_id, entry in entries.items():
        if entry.comparison_id:
            payload[benchmark_id] = {
                "run_id": entry.run_id,
                "comparison_id": entry.comparison_id,
            }
        else:
            payload[benchmark_id] = entry.run_id
    _write_baselines_raw(payload, settings)


def _write_baselines_raw(
    baselines: dict[str, dict[str, str] | str],
    settings: ElenchosSettings | None = None,
) -> None:
    path = _baselines_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(baselines, handle, indent=2)
        handle.write("\n")
    tmp.replace(path)


def clear_baseline(
    benchmark_id: str,
    settings: ElenchosSettings | None = None,
) -> None:
    entries = load_baseline_entries(settings)
    if benchmark_id not in entries:
        return
    del entries[benchmark_id]
    _write_baseline_entries(entries, settings)


def write_baseline_score(run_dir: Path, payload: dict) -> None:
    path = run_dir / "baseline_score.json"
    tmp = path.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
    tmp.replace(path)


def read_baseline_score(run_dir: Path) -> dict | None:
    path = run_dir / "baseline_score.json"
    if not path.is_file():
        return None
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload if isinstance(payload, dict) else None


def delete_run(
    run_id: str,
    settings: ElenchosSettings | None = None,
) -> bool:
    """Remove a run directory from disk. Returns False if the run does not exist."""
    found = find_run(run_id, settings)
    if found is None:
        return False
    run_dir, run = found
    if run.benchmark is not None:
        entries = load_baseline_entries(settings)
        entry = entries.get(run.benchmark.id)
        if entry is not None and entry.run_id == run_id:
            del entries[run.benchmark.id]
            _write_baseline_entries(entries, settings)
    shutil.rmtree(run_dir)
    return True
