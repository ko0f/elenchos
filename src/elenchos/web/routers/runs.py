from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

from elenchos.benchmarks import resolve_benchmark
from elenchos.config import resolve_judge_config
from elenchos.models import (
    Result,
    build_messages,
    default_generation_params,
    generation_params_to_dict,
    parse_model_id,
)
from elenchos.providers.registry import get_provider
from elenchos.providers.base import format_model_output
from elenchos.runner import SuiteRunError, _validate_suite_for_run
from elenchos.baseline import get_or_compute_baseline_comparison
from elenchos.storage import (
    DEFAULT_TASK_ID,
    append_result,
    clear_baseline,
    create_run,
    delete_run,
    finalize_run,
    find_run,
    get_baseline_run_id,
    list_runs,
    load_results,
    read_output,
    save_output,
    set_baseline,
)
from elenchos.web.deps import SettingsDep
from elenchos.web.jobs import job_manager
from elenchos.web.schemas import (
    CreateRunRequest,
    CreateRunResponse,
    PromptRequest,
    PromptResponse,
    RunDetailResponse,
    RunJobResponse,
    RunSummaryResponse,
    baseline_comparison_from_domain,
    result_from_domain,
    run_metadata_from_domain,
    run_summary_from_domain,
)

router = APIRouter(tags=["runs"])


@router.post("/runs", response_model=CreateRunResponse, status_code=202)
def create_run_endpoint(
    request: CreateRunRequest,
    settings: SettingsDep,
) -> CreateRunResponse:
    try:
        suite = resolve_benchmark(request.benchmark)
        judge_config = resolve_judge_config(
            settings=settings,
            cli_judge=request.judge,
        )
        effective_judge = judge_config.model or request.judge
        _validate_suite_for_run(
            suite,
            allow_code_exec=request.allow_code_exec,
            judge_model=effective_judge,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SuiteRunError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    job = job_manager.enqueue_run(
        suite,
        request.model,
        settings=settings,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
        allow_code_exec=request.allow_code_exec,
        judge_model=request.judge,
        concurrency=request.concurrency,
    )
    run_id = job_manager.wait_for_run_id(job.job_id)
    if run_id is None:
        failed = job_manager.get(job.job_id)
        if failed is not None and failed.status == "error":
            raise HTTPException(
                status_code=500,
                detail=failed.error or "Run failed to start",
            ) from None
    return CreateRunResponse(job_id=job.job_id, run_id=run_id)


@router.post("/prompt", response_model=PromptResponse)
def prompt_endpoint(
    request: PromptRequest,
    settings: SettingsDep,
) -> PromptResponse:
    try:
        model_id = parse_model_id(request.model)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    provider = get_provider(model_id.provider, settings=settings)
    if not provider.health_check():
        raise HTTPException(
            status_code=400,
            detail=(
                f"Provider {provider.name!r} is unhealthy at {provider.base_url}."
            ),
        )

    messages = build_messages(request.text)
    params = default_generation_params()
    run_dir, run = create_run(
        model=model_id.qualified,
        params=generation_params_to_dict(params),
        settings=settings,
    )

    try:
        completion = provider.complete(model_id.model, messages, params)
    except Exception as exc:
        result = Result(
            task_id=DEFAULT_TASK_ID,
            prompt=request.text,
            latency_ms=0.0,
            error=str(exc),
        )
        append_result(run_dir, result)
        finalize_run(run_dir, run)
        return PromptResponse(
            run_id=run.run_id,
            output=None,
            latency_ms=0.0,
            error=str(exc),
        )

    formatted = format_model_output(
        text=completion.text,
        reasoning=completion.reasoning,
    )
    output_ref = save_output(run_dir, DEFAULT_TASK_ID, formatted)
    append_result(
        run_dir,
        Result(
            task_id=DEFAULT_TASK_ID,
            prompt=request.text,
            latency_ms=completion.latency_ms,
            prompt_tokens=completion.prompt_tokens,
            completion_tokens=completion.completion_tokens,
            output_ref=output_ref,
            finish_reason=completion.finish_reason,
        ),
    )
    finalize_run(run_dir, run)
    return PromptResponse(
        run_id=run.run_id,
        output=formatted,
        latency_ms=completion.latency_ms,
        prompt_tokens=completion.prompt_tokens,
        completion_tokens=completion.completion_tokens,
        finish_reason=completion.finish_reason,
    )


@router.get("/runs", response_model=list[RunSummaryResponse])
def list_runs_endpoint(settings: SettingsDep) -> list[RunSummaryResponse]:
    summaries: list[RunSummaryResponse] = []
    for run in list_runs(settings):
        comparison = get_or_compute_baseline_comparison(run.run_id, settings)
        summaries.append(run_summary_from_domain(run, comparison=comparison))
    return summaries


@router.delete("/runs/{run_id}", status_code=204)
def delete_run_endpoint(run_id: str, settings: SettingsDep) -> None:
    if not delete_run(run_id, settings):
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")


@router.get("/runs/{run_id}", response_model=RunDetailResponse)
def get_run(run_id: str, settings: SettingsDep) -> RunDetailResponse:
    found = find_run(run_id, settings)
    if found is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    run_dir, run = found
    results = load_results(run_dir, include_output=False)
    comparison = get_or_compute_baseline_comparison(run_id, settings)
    return RunDetailResponse(
        run=run_metadata_from_domain(run),
        results=[result_from_domain(result) for result in results],
        baseline_comparison=baseline_comparison_from_domain(comparison),
    )


@router.post("/runs/{run_id}/baseline", response_model=RunSummaryResponse)
def set_run_baseline(run_id: str, settings: SettingsDep) -> RunSummaryResponse:
    found = find_run(run_id, settings)
    if found is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    _run_dir, run = found
    if run.benchmark is None:
        raise HTTPException(
            status_code=400,
            detail=f"Run {run_id} has no benchmark and cannot be a baseline",
        )
    try:
        set_baseline(run.benchmark.id, run_id, settings)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    comparison = get_or_compute_baseline_comparison(run_id, settings)
    return run_summary_from_domain(run, comparison=comparison)


@router.delete("/runs/{run_id}/baseline", status_code=204)
def clear_run_baseline(run_id: str, settings: SettingsDep) -> None:
    found = find_run(run_id, settings)
    if found is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    _run_dir, run = found
    if run.benchmark is None:
        raise HTTPException(
            status_code=400,
            detail=f"Run {run_id} has no benchmark",
        )
    baseline_run_id = get_baseline_run_id(run.benchmark.id, settings)
    if baseline_run_id != run_id:
        raise HTTPException(
            status_code=400,
            detail=f"Run {run_id} is not the baseline for {run.benchmark.id}",
        )
    clear_baseline(run.benchmark.id, settings)


@router.get("/runs/{run_id}/job", response_model=RunJobResponse)
def get_run_job(run_id: str, settings: SettingsDep) -> RunJobResponse:
    found = find_run(run_id, settings)
    if found is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    job = job_manager.find_by_run_id(run_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"No active job for run: {run_id}")
    return RunJobResponse(job_id=job.job_id)


@router.get(
    "/runs/{run_id}/results/{task_id}/output",
    response_class=PlainTextResponse,
)
def get_task_output(
    run_id: str,
    task_id: str,
    settings: SettingsDep,
) -> str:
    found = find_run(run_id, settings)
    if found is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    run_dir, _run = found
    results = load_results(run_dir, include_output=False)
    result = next((item for item in results if item.task_id == task_id), None)
    if result is None or not result.output_ref:
        raise HTTPException(
            status_code=404,
            detail=f"Result not found for task {task_id!r} in run {run_id}",
        )

    output_path = run_dir / result.output_ref
    if not output_path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"Output file missing for task {task_id!r}",
        )

    return read_output(run_dir, result.output_ref)
