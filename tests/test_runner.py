from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import httpx
import pytest
import yaml

from elenchos.benchmarks.schema import BenchmarkSuite
from elenchos.config import ElenchosSettings
from elenchos.metrics import aggregate_run_summary
from elenchos.models import BenchmarkRef, Result, generation_params_to_dict
from elenchos.providers.base import Completion, GenerationParams, Message
from elenchos.runner import (
    SuiteRunError,
    is_transient_error,
    resolve_generation_params,
    run_suite,
)
from elenchos.storage import append_result, create_run, save_output

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
    call_counts: dict[str, int] = field(default_factory=dict)
    transient_failures: dict[str, int] = field(default_factory=dict)

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
        self.call_counts[prompt] = self.call_counts.get(prompt, 0) + 1

        remaining = self.transient_failures.get(prompt, 0)
        if remaining > 0:
            self.transient_failures[prompt] = remaining - 1
            raise httpx.TimeoutException("simulated timeout")

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


def test_run_suite_resumes_partial_run(
    tiny_suite: BenchmarkSuite, tmp_path, monkeypatch
):
    settings = ElenchosSettings(data_dir=tmp_path)
    run_dir, run = create_run(
        model="mock/mock-model",
        params=generation_params_to_dict(resolve_generation_params(tiny_suite)),
        benchmark=BenchmarkRef(id="tiny-text", version=1),
        settings=settings,
    )
    output_ref = save_output(run_dir, "math", "2")
    append_result(
        run_dir,
        Result(
            task_id="math",
            prompt="What is 1+1? Reply with the number only.",
            latency_ms=10.0,
            score=1.0,
            output_ref=output_ref,
        ),
    )

    provider = MockProvider(
        responses={
            "Name the capital of Italy in one word.": "Rome",
        }
    )

    outcome = run_suite(
        tiny_suite,
        "mock/mock-model",
        provider=provider,
        show_progress=False,
    )

    assert outcome.resumed is True
    assert outcome.run.run_id == run.run_id
    assert len(outcome.results) == 2
    assert provider.call_counts.get("What is 1+1? Reply with the number only.", 0) == 0
    assert provider.call_counts["Name the capital of Italy in one word."] == 1


def test_run_suite_resume_retries_errored_task(
    tiny_suite: BenchmarkSuite, tmp_path, monkeypatch
):
    settings = ElenchosSettings(data_dir=tmp_path)
    run_dir, run = create_run(
        model="mock/mock-model",
        params=generation_params_to_dict(resolve_generation_params(tiny_suite)),
        benchmark=BenchmarkRef(id="tiny-text", version=1),
        settings=settings,
    )
    output_ref = save_output(run_dir, "math", "2")
    append_result(
        run_dir,
        Result(
            task_id="math",
            prompt="What is 1+1? Reply with the number only.",
            latency_ms=10.0,
            score=1.0,
            output_ref=output_ref,
        ),
    )
    append_result(
        run_dir,
        Result(
            task_id="city",
            prompt="Name the capital of Italy in one word.",
            latency_ms=0.0,
            error="provider unavailable",
        ),
    )

    provider = MockProvider(
        responses={"Name the capital of Italy in one word.": "Rome"}
    )

    outcome = run_suite(
        tiny_suite,
        "mock/mock-model",
        provider=provider,
        show_progress=False,
    )

    assert outcome.resumed is True
    assert provider.call_counts.get("What is 1+1? Reply with the number only.", 0) == 0
    assert provider.call_counts["Name the capital of Italy in one word."] == 1
    assert len(outcome.results) == 2
    city = next(result for result in outcome.results if result.task_id == "city")
    assert city.error is None
    assert city.score == 1.0
    assert outcome.summary["errors"] == 0


def test_run_suite_retries_transient_errors(
    tiny_suite: BenchmarkSuite, tmp_path, monkeypatch
):
    city_prompt = "Name the capital of Italy in one word."
    provider = MockProvider(
        responses={
            "What is 1+1? Reply with the number only.": "2",
            city_prompt: "Rome",
        },
        transient_failures={city_prompt: 2},
    )

    outcome = run_suite(
        tiny_suite,
        "mock/mock-model",
        provider=provider,
        show_progress=False,
        max_retries=3,
    )

    assert provider.call_counts[city_prompt] == 3
    assert outcome.results[1].score == 1.0
    assert outcome.summary["errors"] == 0


def test_run_suite_concurrency(tmp_path: Path, monkeypatch):
    suite = BenchmarkSuite.model_validate(
        {
            "id": "parallel",
            "version": 1,
            "type": "text",
            "tasks": [
                {
                    "id": f"t{i}",
                    "prompt": f"prompt-{i}",
                    "scoring": [{"type": "exact_match", "expected": "ok"}],
                }
                for i in range(4)
            ],
        }
    )
    provider = MockProvider(
        responses={f"prompt-{i}": "ok" for i in range(4)},
    )

    outcome = run_suite(
        suite,
        "mock/mock-model",
        provider=provider,
        show_progress=False,
        concurrency=4,
    )

    assert len(outcome.results) == 4
    assert all(result.score == 1.0 for result in outcome.results)


def test_run_suite_on_event_emits_lifecycle(
    tiny_suite: BenchmarkSuite, tmp_path, monkeypatch
):
    provider = MockProvider(
        responses={
            "What is 1+1? Reply with the number only.": "2",
            "Name the capital of Italy in one word.": "Rome",
        }
    )
    events: list[tuple[str, dict]] = []

    def on_event(event: str, data: dict) -> None:
        events.append((event, data))

    outcome = run_suite(
        tiny_suite,
        "mock/mock-model",
        provider=provider,
        show_progress=False,
        on_event=on_event,
    )

    assert [event for event, _data in events] == [
        "run_started",
        "task_done",
        "task_done",
        "run_finished",
    ]
    assert events[0][1]["run_id"] == outcome.run.run_id
    assert events[1][1]["task_id"] == "math"
    assert events[1][1]["index"] == 1
    assert events[1][1]["total"] == 2
    assert events[1][1]["score"] == 1.0
    assert events[2][1]["task_id"] == "city"
    assert events[3][1]["summary"] == outcome.summary


def test_is_transient_error():
    response = httpx.Response(503, request=httpx.Request("POST", "http://test"))
    assert is_transient_error(
        httpx.HTTPStatusError("fail", request=response.request, response=response)
    )
    assert is_transient_error(httpx.TimeoutException("timeout"))
    assert not is_transient_error(RuntimeError("model not found"))
