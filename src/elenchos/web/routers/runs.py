from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

from elenchos.storage import find_run, list_runs, load_results, read_output
from elenchos.web.deps import SettingsDep
from elenchos.web.schemas import (
    RunDetailResponse,
    RunSummaryResponse,
    result_from_domain,
    run_metadata_from_domain,
    run_summary_from_domain,
)

router = APIRouter(tags=["runs"])


@router.get("/runs", response_model=list[RunSummaryResponse])
def list_runs_endpoint(settings: SettingsDep) -> list[RunSummaryResponse]:
    return [run_summary_from_domain(run) for run in list_runs(settings)]


@router.get("/runs/{run_id}", response_model=RunDetailResponse)
def get_run(run_id: str, settings: SettingsDep) -> RunDetailResponse:
    found = find_run(run_id, settings)
    if found is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    run_dir, run = found
    results = load_results(run_dir, include_output=True)
    return RunDetailResponse(
        run=run_metadata_from_domain(run),
        results=[result_from_domain(result) for result in results],
    )


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
