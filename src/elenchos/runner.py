import json
from pathlib import Path
from time import perf_counter

from elenchos.client import create_client, resolve_model
from elenchos.config import Settings
from elenchos.metrics import summarize_results
from elenchos.models import BenchmarkReport, PromptCase, RunResult


def load_prompts(path: Path) -> list[PromptCase]:
    cases: list[PromptCase] = []

    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue

            payload = json.loads(line)
            cases.append(
                PromptCase(
                    id=str(payload.get("id", line_number)),
                    prompt=payload["prompt"],
                    metadata=payload.get("metadata", {}),
                )
            )

    if not cases:
        raise ValueError(f"No prompts found in {path}")

    return cases


def run_benchmark(prompts_path: Path, settings: Settings | None = None) -> Path:
    settings = settings or Settings()
    client = create_client(settings)
    model = resolve_model(client, settings)
    cases = load_prompts(prompts_path)

    report = BenchmarkReport(
        model=model,
        base_url=settings.lm_studio_base_url,
        started_at=BenchmarkReport.now_iso(),
        finished_at="",
    )

    for case in cases:
        report.results.append(_run_case(client, model, case, settings))

    report.finished_at = BenchmarkReport.now_iso()

    output_path = _write_report(report, settings)
    summary = summarize_results(report.results)
    print(json.dumps(summary, indent=2))
    print(f"Wrote report to {output_path}")

    return output_path


def _run_case(
    client,
    model: str,
    case: PromptCase,
    settings: Settings,
) -> RunResult:
    started = perf_counter()

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": case.prompt}],
            temperature=settings.temperature,
            max_tokens=settings.max_tokens,
        )
        latency_ms = (perf_counter() - started) * 1000
        choice = response.choices[0].message.content or ""
        usage = response.usage

        return RunResult(
            case_id=case.id,
            prompt=case.prompt,
            response=choice,
            model=model,
            latency_ms=latency_ms,
            prompt_tokens=getattr(usage, "prompt_tokens", None),
            completion_tokens=getattr(usage, "completion_tokens", None),
            total_tokens=getattr(usage, "total_tokens", None),
        )
    except Exception as exc:
        latency_ms = (perf_counter() - started) * 1000
        return RunResult(
            case_id=case.id,
            prompt=case.prompt,
            response="",
            model=model,
            latency_ms=latency_ms,
            error=str(exc),
        )


def _write_report(report: BenchmarkReport, settings: Settings) -> Path:
    results_dir = Path(settings.results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)

    timestamp = report.started_at.replace(":", "-")
    output_path = results_dir / f"benchmark-{timestamp}.json"

    payload = report.to_dict()
    payload["summary"] = summarize_results(report.results)

    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)

    return output_path
