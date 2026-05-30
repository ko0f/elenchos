from lmbench.models import RunResult


def summarize_results(results: list[RunResult]) -> dict:
    successful = [result for result in results if result.error is None]
    failed = [result for result in results if result.error is not None]

    latencies = [result.latency_ms for result in successful]
    prompt_tokens = [
        result.prompt_tokens for result in successful if result.prompt_tokens is not None
    ]
    completion_tokens = [
        result.completion_tokens
        for result in successful
        if result.completion_tokens is not None
    ]

    return {
        "total": len(results),
        "successful": len(successful),
        "failed": len(failed),
        "latency_ms": {
            "mean": _mean(latencies),
            "p50": _percentile(latencies, 0.5),
            "p95": _percentile(latencies, 0.95),
        },
        "tokens": {
            "prompt_total": sum(prompt_tokens),
            "completion_total": sum(completion_tokens),
        },
    }


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None

    ordered = sorted(values)
    index = int(round((len(ordered) - 1) * percentile))
    return ordered[index]
