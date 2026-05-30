from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse, Response

from elenchos.compare import CompareError
from elenchos.reporter import ReportError, build_leaderboard, format_report
from elenchos.storage import find_comparison, list_comparisons
from elenchos.web.deps import SettingsDep
from elenchos.web.jobs import job_manager
from elenchos.web.schemas import (
    ComparisonDetailResponse,
    ComparisonSummaryResponse,
    CreateCompareRequest,
    CreateCompareResponse,
    LeaderboardResponse,
    ReportRequest,
    comparison_detail_from_dict,
    comparison_summary_from_dict,
    leaderboard_from_domain,
)

router = APIRouter(tags=["compare"])


@router.post("/compare", response_model=CreateCompareResponse, status_code=202)
def create_compare_endpoint(
    request: CreateCompareRequest,
    settings: SettingsDep,
) -> CreateCompareResponse:
    if len(request.run_ids) < 2:
        raise HTTPException(
            status_code=400,
            detail="compare requires at least two run ids",
        )

    mode = (request.mode or "pairwise").lower()
    if mode == "pairwise" and len(request.run_ids) != 2:
        raise HTTPException(
            status_code=400,
            detail="pairwise mode supports exactly two runs; use rubric mode for more.",
        )

    try:
        job = job_manager.enqueue_compare(
            request.run_ids,
            settings=settings,
            mode=mode,
            judge_model=request.judge,
            judge_effort=request.judge_effort,
        )
    except CompareError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return CreateCompareResponse(job_id=job.job_id, comparison_id=job.comparison_id)


@router.get("/comparisons", response_model=list[ComparisonSummaryResponse])
def list_comparisons_endpoint(
    settings: SettingsDep,
) -> list[ComparisonSummaryResponse]:
    return [
        comparison_summary_from_dict(item)
        for item in list_comparisons(settings)
    ]


@router.get("/comparisons/{comparison_id}", response_model=ComparisonDetailResponse)
def get_comparison(
    comparison_id: str,
    settings: SettingsDep,
) -> ComparisonDetailResponse:
    found = find_comparison(comparison_id, settings)
    if found is None:
        raise HTTPException(
            status_code=404,
            detail=f"Comparison not found: {comparison_id}",
        )
    _comp_dir, payload = found
    return comparison_detail_from_dict(payload)


@router.post("/report", response_model=None)
def report_endpoint(request: ReportRequest) -> Response:
    if not request.run_ids:
        raise HTTPException(status_code=400, detail="report requires at least one run id")

    fmt = request.format.lower()
    if fmt not in {"json", "md", "csv"}:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown report format {request.format!r}; expected md, csv, or json.",
        )

    try:
        report = build_leaderboard(request.run_ids)
    except ReportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if fmt == "json":
        return leaderboard_from_domain(report)

    rendered = format_report(report, fmt)
    media_type = "text/markdown" if fmt == "md" else "text/csv"
    return PlainTextResponse(content=rendered, media_type=media_type)
