"""Discover and load benchmark suites from built-in and user directories."""

from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

import yaml
from pydantic import ValidationError

from elenchos.benchmarks.schema import (
    BenchmarkSuite,
    SuiteValidationError,
    format_validation_errors,
)
from elenchos.config import ElenchosSettings


class BenchmarkNotFoundError(LookupError):
    """No benchmark matches the requested id or path."""


@dataclass(frozen=True)
class SuiteSummary:
    id: str
    version: int
    type: str
    description: str
    task_count: int
    source: str
    path: Path


def _settings(settings: ElenchosSettings | None) -> ElenchosSettings:
    return settings or ElenchosSettings()


def builtin_benchmarks_dir() -> Path:
    return Path(str(files("elenchos.benchmarks") / "builtin"))


def user_benchmarks_dir(settings: ElenchosSettings | None = None) -> Path:
    return _settings(settings).data_dir / "benchmarks"


def _yaml_paths(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    paths = list(directory.glob("*.yaml")) + list(directory.glob("*.yml"))
    return sorted(paths, key=lambda path: path.name)


def _read_yaml_mapping(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)
    if not isinstance(payload, dict):
        raise SuiteValidationError(
            f"{path}: expected a YAML mapping at the top level, "
            f"got {type(payload).__name__}"
        )
    return payload


def _peek_suite_id(path: Path) -> str | None:
    try:
        payload = _read_yaml_mapping(path)
    except (OSError, yaml.YAMLError, SuiteValidationError):
        return None
    suite_id = payload.get("id")
    return str(suite_id).strip() if suite_id else None


def discover_suite_paths(settings: ElenchosSettings | None = None) -> dict[str, Path]:
    """Map suite id -> path; user suites override built-ins with the same id."""
    discovered: dict[str, Path] = {}

    for path in _yaml_paths(builtin_benchmarks_dir()):
        suite_id = _peek_suite_id(path)
        if suite_id:
            discovered[suite_id] = path

    for path in _yaml_paths(user_benchmarks_dir(settings)):
        suite_id = _peek_suite_id(path)
        if suite_id:
            discovered[suite_id] = path

    return discovered


def _source_label(path: Path, settings: ElenchosSettings | None) -> str:
    try:
        path.relative_to(builtin_benchmarks_dir())
        return "builtin"
    except ValueError:
        pass
    try:
        path.relative_to(user_benchmarks_dir(settings))
        return "user"
    except ValueError:
        return "file"


def load_suite(path: Path) -> BenchmarkSuite:
    """Load and validate a benchmark suite from a YAML file."""
    try:
        payload = _read_yaml_mapping(path)
    except yaml.YAMLError as exc:
        raise SuiteValidationError(f"{path}: invalid YAML: {exc}") from exc

    try:
        return BenchmarkSuite.model_validate(payload)
    except ValidationError as exc:
        details = format_validation_errors(exc.errors(include_url=False))
        raise SuiteValidationError(
            f"{path}: benchmark validation failed:\n{details}"
        ) from exc


def list_suite_summaries(
    settings: ElenchosSettings | None = None,
) -> list[SuiteSummary]:
    summaries: list[SuiteSummary] = []
    for suite_id, path in sorted(discover_suite_paths(settings).items()):
        try:
            suite = load_suite(path)
        except SuiteValidationError:
            continue
        summaries.append(
            SuiteSummary(
                id=suite.id,
                version=suite.version,
                type=suite.type,
                description=suite.description,
                task_count=len(suite.tasks),
                source=_source_label(path, settings),
                path=path,
            )
        )
    return summaries


def resolve_benchmark(
    ref: str,
    *,
    benchmark_file: Path | None = None,
    settings: ElenchosSettings | None = None,
) -> BenchmarkSuite:
    """Resolve a benchmark by explicit file, path ref, or registered id."""
    if benchmark_file is not None:
        if not benchmark_file.is_file():
            raise BenchmarkNotFoundError(f"Benchmark file not found: {benchmark_file}")
        return load_suite(benchmark_file)

    path_ref = Path(ref)
    if path_ref.suffix in {".yaml", ".yml"} or path_ref.is_file():
        if not path_ref.is_file():
            raise BenchmarkNotFoundError(f"Benchmark file not found: {path_ref}")
        return load_suite(path_ref)

    discovered = discover_suite_paths(settings)
    if ref not in discovered:
        raise BenchmarkNotFoundError(
            f"Benchmark {ref!r} not found. "
            "Try `elenchos bench list` or pass --benchmark-file."
        )
    return load_suite(discovered[ref])


def format_suite_error(exc: Exception) -> str:
    if isinstance(exc, SuiteValidationError):
        return str(exc)
    if isinstance(exc, BenchmarkNotFoundError):
        return str(exc)
    return f"Unexpected error loading benchmark: {exc}"
