from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest
import yaml

from elenchos.benchmarks.schema import BenchmarkSuite
from elenchos.metrics import aggregate_run_summary
from elenchos.providers.base import Completion, GenerationParams, Message
from elenchos.runner import SuiteRunError, run_suite

TINY_SUITE = """\
id: tiny-text
version: 1
type: text
tasks:
  - id: math
    prompt: What is 1+1? Reply with the number only.
    scoring:
      - type: exact_match
        expected: "2"
  - id: city
    prompt: Name the capital of Italy in one word.
    scoring:
      - type: contains_all
        strings:
          - Rome
"""


@dataclass
class MockProvider:
    name: str = "mock"
    responses: dict[str, str] = field(default_factory=dict)
    fail_prompts: set[str] = field(default_factory=set)

    def list_models(self) -> list[str]:
        return ["mock-model"]

    def health_check(self) -> bool:
        return True

    def complete(
        self,
        model: str,
        messages: list[Message],
        params: GenerationParams,
    ) -> Completion:
        prompt = messages[-1].content
        if prompt in self.fail_prompts:
            raise RuntimeError("provider unavailable")

        text = self.responses.get(prompt, "wrong")
        return Completion(
            text=text,
            prompt_tokens=10,
            completion_tokens=3,
            latency_ms=42.0,
            raw={},
            finish_reason="stop",
        )


@pytest.fixture
def tiny_suite(tmp_path: Path) -> BenchmarkSuite:
    path = tmp_path / "tiny.yaml"
    path.write_text(TINY_SUITE, encoding="utf-8")
    return BenchmarkSuite.model_validate(yaml.safe_load(TINY_SUITE))


def test_run_suite_with_mock_provider(
    tiny_suite: BenchmarkSuite, tmp_path, monkeypatch
):
    monkeypatch.setenv("ELENCHOS_DATA_DIR", str(tmp_path))

    provider = MockProvider(
        responses={
            "What is 1+1? Reply with the number only.": "2",
            "Name the capital of Italy in one word.": "Rome",
        }
    )

    outcome = run_suite(
        tiny_suite,
        "mock/mock-model",
        provider=provider,
        show_progress=False,
    )

    assert outcome.run.benchmark is not None
    assert outcome.run.benchmark.id == "tiny-text"
    assert len(outcome.results) == 2
    assert all(result.score == 1.0 for result in outcome.results)
    assert outcome.summary["mean_score"] == 1.0
    assert outcome.summary["pass_rate"] == 1.0
    assert outcome.summary["task_count"] == 2
    assert (outcome.run_dir / "results.jsonl").is_file()
    assert (outcome.run_dir / "outputs" / "math.txt").read_text() == "2"


def test_run_suite_records_task_errors(
    tiny_suite: BenchmarkSuite, tmp_path, monkeypatch
):
    monkeypatch.setenv("ELENCHOS_DATA_DIR", str(tmp_path))

    provider = MockProvider(
        responses={"What is 1+1? Reply with the number only.": "2"},
        fail_prompts={"Name the capital of Italy in one word."},
    )

    outcome = run_suite(
        tiny_suite,
        "mock/mock-model",
        provider=provider,
        show_progress=False,
    )

    assert outcome.results[0].score == 1.0
    assert outcome.results[1].error == "provider unavailable"
    assert outcome.summary["errors"] == 1
    assert outcome.summary["pass_rate"] == 0.5


def test_run_suite_rejects_coding_suite_without_flag(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ELENCHOS_DATA_DIR", str(tmp_path))
    suite = BenchmarkSuite.model_validate(
        {
            "id": "coding",
            "version": 1,
            "type": "coding",
            "tasks": [
                {
                    "id": "fizz",
                    "prompt": "Write fizzbuzz.",
                    "scoring": [
                        {
                            "type": "unit_test",
                            "language": "python",
                            "entrypoint": "fizzbuzz",
                            "tests": "assert True",
                        }
                    ],
                }
            ],
        }
    )

    with pytest.raises(SuiteRunError, match="allow-code-exec"):
        run_suite(
            suite,
            "mock/mock-model",
            provider=MockProvider(),
            show_progress=False,
        )


CODING_SUITE = """\
id: tiny-coding
version: 1
type: coding
tasks:
  - id: add
    prompt: Write add(a, b).
    scoring:
      - type: unit_test
        language: python
        entrypoint: add
        tests: |
          assert add(1, 2) == 3
          assert add(0, 0) == 0
"""


def test_run_suite_coding_with_mock_provider(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ELENCHOS_DATA_DIR", str(tmp_path))
    suite = BenchmarkSuite.model_validate(yaml.safe_load(CODING_SUITE))

    good_code = "def add(a, b):\n    return a + b\n"
    provider = MockProvider(
        responses={"Write add(a, b).": good_code},
    )

    outcome = run_suite(
        suite,
        "mock/mock-model",
        provider=provider,
        show_progress=False,
        allow_code_exec=True,
    )

    assert len(outcome.results) == 1
    assert outcome.results[0].score == 1.0
    assert outcome.results[0].passed == 2
    assert outcome.results[0].total == 2


def test_aggregate_run_summary():
    from elenchos.models import Result

    summary = aggregate_run_summary(
        [
            Result(task_id="a", latency_ms=100.0, score=1.0),
            Result(task_id="b", latency_ms=200.0, score=0.5),
            Result(task_id="c", latency_ms=50.0, error="boom"),
        ]
    )

    assert summary["task_count"] == 3
    assert summary["mean_score"] == 0.75
    assert summary["pass_rate"] == pytest.approx(1 / 3)
    assert summary["errors"] == 1
    assert summary["p95_latency_ms"] == 200.0
