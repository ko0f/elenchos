from elenchos.models import Result, RunResult


def summarize_results(results: list[RunResult]) -> dict:
    successful = [result for result in results if result.error is None]
    failed = [result for result in results if result.error is not None]

    latencies = [result.latency_ms for result in successful]
    prompt_tokens = [
        result.prompt_tokens
        for result in successful
        if result.prompt_tokens is not None
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


def aggregate_run_summary(results: list[Result]) -> dict:
    """Aggregate scored benchmark task results for ``run.json`` summary."""
    total = len(results)
    successful = [result for result in results if result.error is None]
    errors = total - len(successful)
    scored = [result for result in successful if result.score is not None]
    latencies = [result.latency_ms for result in successful]

    mean_score = _mean([result.score for result in scored])
    pass_count = sum(1 for result in scored if result.score >= 1.0)
    pass_rate = pass_count / total if total else None

    return {
        "task_count": total,
        "mean_score": mean_score,
        "pass_rate": pass_rate,
        "p95_latency_ms": _percentile(latencies, 0.95),
        "errors": errors,
    }
