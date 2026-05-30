from lmbench.metrics import summarize_results
from lmbench.models import RunResult


def test_summarize_results():
    results = [
        RunResult(
            case_id="a",
            prompt="p",
            response="r",
            model="test",
            latency_ms=100.0,
            prompt_tokens=10,
            completion_tokens=5,
        ),
        RunResult(
            case_id="b",
            prompt="p",
            response="",
            model="test",
            latency_ms=50.0,
            error="boom",
        ),
    ]

    summary = summarize_results(results)

    assert summary["total"] == 2
    assert summary["successful"] == 1
    assert summary["failed"] == 1
    assert summary["latency_ms"]["mean"] == 100.0
    assert summary["tokens"]["prompt_total"] == 10
    assert summary["tokens"]["completion_total"] == 5
