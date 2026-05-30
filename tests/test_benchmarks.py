from pathlib import Path

import pytest
import yaml

from elenchos.benchmarks.registry import (
    BenchmarkNotFoundError,
    discover_suite_paths,
    load_suite,
    resolve_benchmark,
)
from elenchos.benchmarks.schema import BenchmarkSuite, SuiteValidationError

VALID_SUITE = """\
id: sample-suite
version: 1
type: text
description: A tiny suite for tests.
tasks:
  - id: hello
    prompt: Say hello.
    scoring:
      - type: exact_match
        expected: hello
"""


def test_valid_suite_loads(tmp_path: Path):
    path = tmp_path / "sample.yaml"
    path.write_text(VALID_SUITE, encoding="utf-8")

    suite = load_suite(path)

    assert suite.id == "sample-suite"
    assert suite.version == 1
    assert suite.type == "text"
    assert len(suite.tasks) == 1
    assert suite.tasks[0].id == "hello"
    assert suite.effective_scoring(suite.tasks[0])[0].type == "exact_match"


@pytest.mark.parametrize(
    "payload, match",
    [
        (
            {"id": "x", "version": 1, "type": "text", "tasks": []},
            "tasks",
        ),
        (
            {
                "id": "x",
                "version": 1,
                "type": "text",
                "tasks": [
                    {"id": "a", "prompt": "one"},
                    {"id": "a", "prompt": "two"},
                ],
            },
            "duplicate task ids",
        ),
        (
            {
                "id": "x",
                "version": 1,
                "type": "text",
                "tasks": [{"id": "a", "prompt": "hi", "scoring": [{"type": "nope"}]}],
            },
            "scoring",
        ),
    ],
)
def test_invalid_suite_raises_clear_error(
    tmp_path: Path,
    payload: dict,
    match: str,
):
    path = tmp_path / "broken.yaml"
    path.write_text(yaml.dump(payload), encoding="utf-8")

    with pytest.raises(SuiteValidationError, match=match):
        load_suite(path)


def test_registry_includes_builtin_suite():
    discovered = discover_suite_paths()
    assert "text-reasoning-v1" in discovered
    assert "coding-basics-v1" in discovered

    suite = load_suite(discovered["text-reasoning-v1"])
    assert suite.id == "text-reasoning-v1"
    assert len(suite.tasks) >= 3

    coding = load_suite(discovered["coding-basics-v1"])
    assert coding.type == "coding"
    assert len(coding.tasks) == 8


def test_user_suite_overrides_builtin(tmp_path, monkeypatch):
    user_dir = tmp_path / "benchmarks"
    user_dir.mkdir()
    monkeypatch.setenv("ELENCHOS_DATA_DIR", str(tmp_path))

    (user_dir / "text-reasoning-v1.yaml").write_text(
        VALID_SUITE.replace("sample-suite", "text-reasoning-v1"),
        encoding="utf-8",
    )

    discovered = discover_suite_paths()
    suite = load_suite(discovered["text-reasoning-v1"])

    assert suite.id == "text-reasoning-v1"
    assert suite.description == "A tiny suite for tests."
    assert len(suite.tasks) == 1


def test_resolve_by_id_and_file(tmp_path: Path):
    path = tmp_path / "custom.yaml"
    path.write_text(VALID_SUITE, encoding="utf-8")

    by_path = resolve_benchmark(str(path))
    assert by_path.id == "sample-suite"

    by_file = resolve_benchmark("ignored", benchmark_file=path)
    assert by_file.id == "sample-suite"

    with pytest.raises(BenchmarkNotFoundError, match="not found"):
        resolve_benchmark("missing-suite-id")


def test_benchmark_suite_round_trip():
    suite = BenchmarkSuite.model_validate(yaml.safe_load(VALID_SUITE))
    restored = BenchmarkSuite.model_validate(suite.model_dump())
    assert restored == suite
