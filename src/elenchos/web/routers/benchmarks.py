from fastapi import APIRouter

from elenchos.benchmarks import list_suite_summaries, resolve_benchmark
from elenchos.web.deps import SettingsDep
from elenchos.web.schemas import (
    SuiteDetailResponse,
    SuiteSummaryResponse,
    suite_detail_from_domain,
    suite_summary_from_domain,
)

router = APIRouter(tags=["benchmarks"])


@router.get("/benchmarks", response_model=list[SuiteSummaryResponse])
def list_benchmarks(settings: SettingsDep) -> list[SuiteSummaryResponse]:
    return [
        suite_summary_from_domain(summary)
        for summary in list_suite_summaries(settings)
    ]


@router.get("/benchmarks/{benchmark_id}", response_model=SuiteDetailResponse)
def get_benchmark(benchmark_id: str, settings: SettingsDep) -> SuiteDetailResponse:
    suite = resolve_benchmark(benchmark_id, settings=settings)
    return suite_detail_from_domain(suite)
