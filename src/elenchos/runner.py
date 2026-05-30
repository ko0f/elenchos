"""Benchmark suite orchestration."""

from __future__ import annotations

import contextlib
import json
import logging
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import httpx

from elenchos.benchmarks.schema import BenchmarkSuite, GenerationParamsDefaults, Task
from elenchos.config import ElenchosSettings, resolve_judge_config, resolve_run_defaults
from elenchos.console import console
from elenchos.metrics import aggregate_run_summary
from elenchos.models import (
    BenchmarkRef,
    PromptCase,
    Result,
    Run,
    build_messages,
    generation_params_to_dict,
    parse_model_id,
)
from elenchos.providers.base import GenerationParams, Message, Provider
from elenchos.providers.registry import get_provider
from elenchos.scoring.deterministic import score_task_output
from elenchos.scoring.judge import JudgeContext
from elenchos.storage import (
    append_result,
    create_run,
    finalize_run,
    find_resumable_run,
    load_results,
    rewrite_results,
    save_output,
)

logger = logging.getLogger(__name__)

TEXT_SCORERS = frozenset(
    {"exact_match", "regex_match", "contains_all", "judge_rubric", "metrics"}
)
CODING_SCORERS = frozenset({"unit_test", "metrics"})

_TRANSIENT_HTTP = frozenset({408, 429, 500, 502, 503, 504})


class SuiteRunError(ValueError):
    """Benchmark run cannot proceed."""


@dataclass
class SuiteRunOutcome:
    run: Run
    run_dir: Path
    results: list[Result]
    summary: dict
    resumed: bool = False


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


def resolve_generation_params(
    suite: BenchmarkSuite,
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> GenerationParams:
    defaults = (
        suite.defaults.params
        if suite.defaults and suite.defaults.params
        else GenerationParamsDefaults()
    )
    return GenerationParams(
        temperature=defaults.temperature if temperature is None else temperature,
        top_p=defaults.top_p if defaults.top_p is not None else 1.0,
        max_tokens=defaults.max_tokens if max_tokens is None else max_tokens,
        seed=defaults.seed,
        stop=defaults.stop,
    )


def is_transient_error(exc: Exception) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _TRANSIENT_HTTP
    return isinstance(
        exc,
        (
            httpx.TimeoutException,
            httpx.ConnectError,
            httpx.ReadError,
            httpx.RemoteProtocolError,
            httpx.NetworkError,
        ),
    )


def complete_with_retry(
    provider: Provider,
    model: str,
    messages: list[Message],
    params: GenerationParams,
    *,
    max_attempts: int = 3,
    base_delay: float = 1.0,
):
    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return provider.complete(model, messages, params)
        except Exception as exc:
            last_exc = exc
            if not is_transient_error(exc) or attempt >= max_attempts - 1:
                raise
            delay = base_delay * (2**attempt) + random.uniform(0, 0.1)
            logger.warning(
                "Transient provider error (attempt %d/%d): %s; retry in %.1fs",
                attempt + 1,
                max_attempts,
                exc,
                delay,
            )
            time.sleep(delay)
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("complete_with_retry exhausted without result")


def _suite_needs_judge(suite: BenchmarkSuite) -> bool:
    for task in suite.tasks:
        for scorer in suite.effective_scoring(task):
            if scorer.type == "judge_rubric":
                return True
    return False


def _build_judge_context(
    judge_model: str,
    *,
    settings: ElenchosSettings | None = None,
) -> JudgeContext:
    model_id = parse_model_id(judge_model)
    provider = get_provider(model_id.provider, settings=settings)
    return JudgeContext(
        provider=provider,
        model=model_id.model,
        qualified=model_id.qualified,
    )


def _validate_suite_for_run(
    suite: BenchmarkSuite,
    *,
    allow_code_exec: bool,
    judge_model: str | None = None,
) -> None:
    has_unit_test = False

    if _suite_needs_judge(suite) and not judge_model:
        raise SuiteRunError(
            "Benchmark uses judge_rubric scoring. Pass --judge or set "
            "judge.model in ~/.elenchos/config.yaml."
        )

    for task in suite.tasks:
        task_type = suite.effective_task_type(task)
        for scorer in suite.effective_scoring(task):
            if scorer.type == "unit_test":
                has_unit_test = True
            elif task_type == "text" and scorer.type not in TEXT_SCORERS:
                raise SuiteRunError(
                    f"Task {task.id!r} uses scorer {scorer.type!r}; "
                    "only exact_match, regex_match, and contains_all are "
                    "supported for text tasks."
                )
            elif task_type == "coding" and scorer.type not in CODING_SCORERS:
                raise SuiteRunError(
                    f"Task {task.id!r} uses scorer {scorer.type!r}; "
                    "coding tasks require unit_test scoring."
                )

    if has_unit_test and not allow_code_exec:
        raise SuiteRunError(
            "Benchmark includes unit_test scoring, which executes untrusted "
            "model-generated code. Re-run with --allow-code-exec to proceed."
        )


def _run_task(
    *,
    provider: Provider,
    model_name: str,
    params: GenerationParams,
    suite: BenchmarkSuite,
    task: Task,
    allow_code_exec: bool = False,
    judge: JudgeContext | None = None,
    max_retries: int = 3,
) -> Result:
    messages = build_messages(task.prompt)
    scorers = suite.effective_scoring(task)

    try:
        completion = complete_with_retry(
            provider,
            model_name,
            messages,
            params,
            max_attempts=max_retries,
        )
    except Exception as exc:
        logger.exception("Task %s failed", task.id)
        return Result(
            task_id=task.id,
            prompt=task.prompt,
            latency_ms=0.0,
            error=str(exc),
        )

    score_outcome = score_task_output(
        completion.text,
        scorers,
        prompt=task.prompt,
        judge=judge,
        allow_code_exec=allow_code_exec,
    )
    return Result(
        task_id=task.id,
        prompt=task.prompt,
        latency_ms=completion.latency_ms,
        prompt_tokens=completion.prompt_tokens,
        completion_tokens=completion.completion_tokens,
        finish_reason=completion.finish_reason,
        score=score_outcome.score,
        scorer=score_outcome.scorer,
        passed=score_outcome.passed,
        total=score_outcome.total,
        output=completion.text,
    )


def _persist_result(run_dir: Path, result: Result) -> Result:
    if result.error:
        append_result(run_dir, result)
        return result

    output_ref = save_output(run_dir, result.task_id, result.output or "")
    result.output_ref = output_ref
    append_result(run_dir, result)
    return result


def _print_task_outcome(label: str, result: Result) -> None:
    if result.error:
        console.print(f"[red]{label} error:[/red] {result.error}")
        return
    if result.score is None:
        return
    if result.score >= 1.0:
        console.print(f"[green]{label}[/green] score={result.score:.2f}")
    elif result.score > 0:
        console.print(f"[yellow]{label}[/yellow] score={result.score:.2f}")
    else:
        console.print(f"[red]{label}[/red] score={result.score:.2f}")


def _execute_tasks(
    *,
    suite: BenchmarkSuite,
    pending_tasks: list[Task],
    provider: Provider,
    model_name: str,
    params: GenerationParams,
    run_dir: Path,
    allow_code_exec: bool,
    judge_ctx: JudgeContext | None,
    max_retries: int,
    concurrency: int,
    show_progress: bool,
    task_index_offset: int,
) -> list[Result]:
    if not pending_tasks:
        return []

    write_lock = threading.Lock()
    new_results: list[Result] = []

    if concurrency <= 1:
        for index, task in enumerate(pending_tasks, start=1):
            absolute_index = task_index_offset + index
            label = f"[{absolute_index}/{len(suite.tasks)}] {task.id}"
            status = (
                console.status(label) if show_progress else contextlib.nullcontext()
            )
            with status:
                result = _run_task(
                    provider=provider,
                    model_name=model_name,
                    params=params,
                    suite=suite,
                    task=task,
                    allow_code_exec=allow_code_exec,
                    judge=judge_ctx,
                    max_retries=max_retries,
                )
                with write_lock:
                    result = _persist_result(run_dir, result)
            new_results.append(result)
            if show_progress:
                _print_task_outcome(label, result)
        return new_results

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        future_to_task = {
            executor.submit(
                _run_task,
                provider=provider,
                model_name=model_name,
                params=params,
                suite=suite,
                task=task,
                allow_code_exec=allow_code_exec,
                judge=judge_ctx,
                max_retries=max_retries,
            ): task
            for task in pending_tasks
        }
        for future in as_completed(future_to_task):
            task = future_to_task[future]
            label = task.id
            try:
                result = future.result()
            except Exception as exc:
                logger.exception("Task %s worker failed", task.id)
                result = Result(
                    task_id=task.id,
                    prompt=task.prompt,
                    latency_ms=0.0,
                    error=str(exc),
                )
            with write_lock:
                result = _persist_result(run_dir, result)
            new_results.append(result)
            if show_progress:
                _print_task_outcome(label, result)

    return new_results


def _order_results(suite: BenchmarkSuite, results: list[Result]) -> list[Result]:
    order = {task.id: index for index, task in enumerate(suite.tasks)}
    return sorted(results, key=lambda result: order.get(result.task_id, len(order)))


def run_suite(
    suite: BenchmarkSuite,
    model: str,
    *,
    provider: Provider | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    settings: ElenchosSettings | None = None,
    show_progress: bool = True,
    allow_code_exec: bool = False,
    judge_model: str | None = None,
    concurrency: int | None = None,
    max_retries: int | None = None,
) -> SuiteRunOutcome:
    """Run benchmark tasks with optional concurrency, resume, and retries."""
    settings = settings or ElenchosSettings()
    effective_concurrency, effective_max_retries = resolve_run_defaults(
        settings=settings,
        cli_concurrency=concurrency,
        cli_max_retries=max_retries,
    )
    if effective_concurrency < 1:
        raise SuiteRunError("concurrency must be at least 1")

    try:
        judge_config = resolve_judge_config(settings=settings, cli_judge=judge_model)
    except ValueError as exc:
        raise SuiteRunError(str(exc)) from exc
    effective_judge = judge_config.model or judge_model

    _validate_suite_for_run(
        suite,
        allow_code_exec=allow_code_exec,
        judge_model=effective_judge,
    )

    model_id = parse_model_id(model)
    provider = provider or get_provider(model_id.provider)
    params = resolve_generation_params(
        suite,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    if not provider.health_check():
        raise SuiteRunError(
            f"Provider {provider.name!r} is unhealthy at {provider.base_url}."
        )

    judge_ctx: JudgeContext | None = None
    if effective_judge and _suite_needs_judge(suite):
        judge_ctx = _build_judge_context(effective_judge, settings=settings)
        if not judge_ctx.provider.health_check():
            raise SuiteRunError(
                f"Judge provider {judge_ctx.provider.name!r} is unhealthy at "
                f"{judge_ctx.provider.base_url}."
            )

    benchmark = BenchmarkRef(id=suite.id, version=suite.version)
    resumed = False
    resumable = find_resumable_run(
        suite.id,
        model_id.qualified,
        version=suite.version,
        params=generation_params_to_dict(params),
        settings=settings,
    )
    if resumable is not None:
        run_dir, run = resumable
        resumed = True
        prior_results = load_results(run_dir, include_output=False)
        existing_results = [r for r in prior_results if r.error is None]
        completed_ids = {result.task_id for result in existing_results}
        if len(existing_results) != len(prior_results):
            # Drop errored rows so retried tasks don't leave stale duplicates.
            rewrite_results(run_dir, existing_results)
        if show_progress and completed_ids:
            console.print(
                f"[dim]Resuming run {run.run_id}; "
                f"skipping {len(completed_ids)} completed task(s)[/dim]"
            )
    else:
        run_dir, run = create_run(
            model=model_id.qualified,
            params=generation_params_to_dict(params),
            benchmark=benchmark,
            settings=settings,
        )
        existing_results = []
        completed_ids = set()

    pending_tasks = [task for task in suite.tasks if task.id not in completed_ids]
    task_index_offset = len(completed_ids)

    new_results = _execute_tasks(
        suite=suite,
        pending_tasks=pending_tasks,
        provider=provider,
        model_name=model_id.model,
        params=params,
        run_dir=run_dir,
        allow_code_exec=allow_code_exec,
        judge_ctx=judge_ctx,
        max_retries=effective_max_retries,
        concurrency=effective_concurrency,
        show_progress=show_progress,
        task_index_offset=task_index_offset,
    )

    results = _order_results(suite, existing_results + new_results)
    summary = aggregate_run_summary(results)
    run.summary = summary
    finalize_run(run_dir, run)

    return SuiteRunOutcome(
        run=run,
        run_dir=run_dir,
        results=results,
        summary=summary,
        resumed=resumed,
    )
