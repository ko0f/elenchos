import asyncio
import json

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

from elenchos.web.jobs import job_manager
from elenchos.web.schemas import JobStatusResponse, job_status_from_domain

router = APIRouter(tags=["jobs"])


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
def get_job(job_id: str) -> JobStatusResponse:
    job = job_manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    return job_status_from_domain(job)


@router.get("/jobs/{job_id}/events")
async def stream_job_events(job_id: str) -> EventSourceResponse:
    if job_manager.get(job_id) is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    async def event_generator():
        seen = 0
        while True:
            job, events = job_manager.snapshot_progress(job_id, seen)
            if job is None:
                break

            for progress_event in events:
                seen += 1
                yield {
                    "event": progress_event.event,
                    "data": json.dumps(progress_event.data),
                }

            if job.status == "error":
                yield {
                    "event": "job_error",
                    "data": json.dumps({"detail": job.error or "Job failed"}),
                }
                break

            if job.status == "done":
                break

            await asyncio.to_thread(
                job_manager.wait_for_progress,
                job_id,
                seen=seen,
                timeout=30.0,
            )

    return EventSourceResponse(event_generator())
