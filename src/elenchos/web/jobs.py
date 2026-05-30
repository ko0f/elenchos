"""In-process job queue for long-running benchmark operations."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from elenchos.benchmarks.schema import BenchmarkSuite
from elenchos.compare import CompareError, compare_runs
from elenchos.config import ElenchosSettings
from elenchos.runner import RunEventCallback, SuiteRunError, run_suite

JobKind = Literal["run", "compare"]
JobStatus = Literal["queued", "running", "done", "error"]


@dataclass
class ProgressEvent:
    event: str
    data: dict[str, Any]


@dataclass
class Job:
    job_id: str
    kind: JobKind
    status: JobStatus = "queued"
    run_id: str | None = None
    comparison_id: str | None = None
    progress: list[ProgressEvent] = field(default_factory=list)
    result: dict[str, Any] | None = None
    error: str | None = None


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._conditions: dict[str, threading.Condition] = {}

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def find_by_run_id(self, run_id: str) -> Job | None:
        with self._lock:
            for job in self._jobs.values():
                if job.run_id == run_id and job.status in ("queued", "running"):
                    return job
        return None

    def _notify(self, job_id: str) -> None:
        with self._lock:
            condition = self._conditions.get(job_id)
        if condition is not None:
            with condition:
                condition.notify_all()

    def _register_job(self, job: Job) -> threading.Condition:
        with self._lock:
            self._jobs[job.job_id] = job
            condition = threading.Condition()
            self._conditions[job.job_id] = condition
            return condition

    def enqueue_run(
        self,
        suite: BenchmarkSuite,
        model: str,
        *,
        settings: ElenchosSettings,
        temperature: float | None = None,
        max_tokens: int | None = None,
        allow_code_exec: bool = False,
        judge_model: str | None = None,
        concurrency: int | None = None,
    ) -> Job:
        job = Job(job_id=uuid.uuid4().hex, kind="run")
        self._register_job(job)

        thread = threading.Thread(
            target=self._run_suite_worker,
            args=(job, suite, model),
            kwargs={
                "settings": settings,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "allow_code_exec": allow_code_exec,
                "judge_model": judge_model,
                "concurrency": concurrency,
            },
            daemon=True,
            name=f"elenchos-run-{job.job_id[:8]}",
        )
        thread.start()
        return job

    def enqueue_compare(
        self,
        run_ids: list[str],
        *,
        settings: ElenchosSettings,
        mode: str | None = None,
        judge_model: str | None = None,
    ) -> Job:
        job = Job(job_id=uuid.uuid4().hex, kind="compare")
        self._register_job(job)

        thread = threading.Thread(
            target=self._compare_worker,
            args=(job, run_ids),
            kwargs={
                "settings": settings,
                "mode": mode,
                "judge_model": judge_model,
            },
            daemon=True,
            name=f"elenchos-compare-{job.job_id[:8]}",
        )
        thread.start()
        return job

    def _compare_worker(
        self,
        job: Job,
        run_ids: list[str],
        *,
        settings: ElenchosSettings,
        mode: str | None,
        judge_model: str | None,
    ) -> None:
        job.status = "running"

        def on_event(event: str, data: dict[str, Any]) -> None:
            with self._lock:
                job.progress.append(ProgressEvent(event=event, data=data))
                if event == "compare_started":
                    job.comparison_id = data["comparison_id"]
                if event == "compare_finished":
                    job.result = data
            self._notify(job.job_id)

        try:
            artifact, _out_path = compare_runs(
                run_ids,
                mode=mode,
                judge_model=judge_model,
                settings=settings,
                on_event=on_event,
            )
        except CompareError as exc:
            with self._lock:
                job.status = "error"
                job.error = str(exc)
            self._notify(job.job_id)
            return
        except Exception as exc:
            with self._lock:
                job.status = "error"
                job.error = str(exc)
            self._notify(job.job_id)
            return

        with self._lock:
            job.status = "done"
            job.comparison_id = artifact.comparison_id
            if job.result is None:
                job.result = {
                    "comparison_id": artifact.comparison_id,
                    "summary": artifact.summary,
                }
        self._notify(job.job_id)

    def _run_suite_worker(
        self,
        job: Job,
        suite: BenchmarkSuite,
        model: str,
        *,
        settings: ElenchosSettings,
        temperature: float | None,
        max_tokens: int | None,
        allow_code_exec: bool,
        judge_model: str | None,
        concurrency: int | None,
    ) -> None:
        job.status = "running"

        def on_event(event: str, data: dict[str, Any]) -> None:
            with self._lock:
                job.progress.append(ProgressEvent(event=event, data=data))
                if event == "run_started":
                    job.run_id = data["run_id"]
                if event == "run_finished":
                    job.result = data
            self._notify(job.job_id)

        try:
            outcome = run_suite(
                suite,
                model,
                settings=settings,
                temperature=temperature,
                max_tokens=max_tokens,
                show_progress=False,
                allow_code_exec=allow_code_exec,
                judge_model=judge_model,
                concurrency=concurrency,
                on_event=on_event,
            )
        except SuiteRunError as exc:
            with self._lock:
                job.status = "error"
                job.error = str(exc)
            self._notify(job.job_id)
            return
        except Exception as exc:
            with self._lock:
                job.status = "error"
                job.error = str(exc)
            self._notify(job.job_id)
            return

        with self._lock:
            job.status = "done"
            job.run_id = outcome.run.run_id
        self._notify(job.job_id)

    def wait_for_progress(
        self,
        job_id: str,
        *,
        seen: int,
        timeout: float = 0.5,
    ) -> tuple[Job | None, int]:
        with self._lock:
            job = self._jobs.get(job_id)
            condition = self._conditions.get(job_id)
            current_seen = len(job.progress) if job is not None else seen

        if job is None:
            return None, seen

        if current_seen > seen:
            return job, current_seen

        if job.status in ("done", "error"):
            return job, current_seen

        if condition is None:
            return job, current_seen

        with condition:
            condition.wait(timeout=timeout)

        with self._lock:
            job = self._jobs.get(job_id)
            current_seen = len(job.progress) if job is not None else seen
        return job, current_seen

    def snapshot_progress(
        self,
        job_id: str,
        seen: int,
    ) -> tuple[Job | None, list[ProgressEvent]]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None, []
            return job, list(job.progress[seen:])


job_manager = JobManager()
