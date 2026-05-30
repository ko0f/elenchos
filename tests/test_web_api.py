import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from fastapi.testclient import TestClient

from elenchos.config import ElenchosSettings
from elenchos.models import BenchmarkRef, Result
from elenchos.runner import SuiteRunOutcome
from elenchos.storage import (
    append_result,
    create_run,
    finalize_run,
    save_output,
)
from elenchos.web.app import create_app
from elenchos.web.deps import get_settings
from elenchos.web.jobs import job_manager


@pytest.fixture
def api_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ELENCHOS_DATA_DIR", str(tmp_path))
    settings = ElenchosSettings(
        data_dir=tmp_path,
        ollama_base_url=None,
        ollama_api_key=None,
        lmstudio_base_url=None,
        lmstudio_api_key=None,
        openrouter_base_url=None,
        openrouter_api_key=None,
    )
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as client:
        yield client, settings
    app.dependency_overrides.clear()
    get_settings.cache_clear()


@pytest.fixture
def seeded_run(api_client):
    client, settings = api_client
    run_dir, run = create_run(
        model="ollama/llama3.1:8b",
        params={"temperature": 0.0, "max_tokens": 1024},
        benchmark=BenchmarkRef(id="text-reasoning-v1", version=1),
        settings=settings,
    )
    output_ref = save_output(run_dir, "arithmetic", "4")
    append_result(
        run_dir,
        Result(
            task_id="arithmetic",
            prompt="What is 2+2?",
            latency_ms=150.0,
            prompt_tokens=8,
            completion_tokens=1,
            output_ref=output_ref,
            score=1.0,
            scorer="exact_match",
            finish_reason="stop",
        ),
    )
    run.summary = {"mean_score": 1.0, "pass_rate": 1.0, "p95_latency_ms": 150.0}
    finalize_run(run_dir, run)
    return client, run


def test_list_benchmarks(api_client):
    client, _settings = api_client
    response = client.get("/api/benchmarks")
    assert response.status_code == 200
    suites = response.json()
    ids = {suite["id"] for suite in suites}
    assert "coding-basics-v1" in ids
    assert "text-reasoning-v1" in ids
    sample = next(item for item in suites if item["id"] == "coding-basics-v1")
    assert sample["source"] == "builtin"
    assert sample["task_count"] >= 1


def test_get_coding_benchmark_requires_code_exec(api_client):
    client, _settings = api_client
    response = client.get("/api/benchmarks/coding-basics-v1")
    assert response.status_code == 200
    payload = response.json()
    assert payload["requires_code_exec"] is True
    assert payload["requires_judge"] is False
    assert payload["tasks"][0]["scorers"] == ["unit_test"]


def test_get_text_benchmark_no_code_exec(api_client):
    client, _settings = api_client
    response = client.get("/api/benchmarks/text-reasoning-v1")
    assert response.status_code == 200
    payload = response.json()
    assert payload["requires_code_exec"] is False
    assert payload["requires_judge"] is False


def test_get_benchmark_requires_judge(api_client):
    client, settings = api_client
    benchmarks_dir = settings.data_dir / "benchmarks"
    benchmarks_dir.mkdir(parents=True)
    suite = {
        "id": "judge-suite-v1",
        "version": 1,
        "type": "text",
        "description": "Judge rubric suite for API tests.",
        "tasks": [
            {
                "id": "essay",
                "prompt": "Explain recursion briefly.",
                "scoring": [{"type": "judge_rubric", "rubric": "Clear and accurate."}],
            }
        ],
    }
    (benchmarks_dir / "judge-suite-v1.yaml").write_text(
        yaml.dump(suite),
        encoding="utf-8",
    )

    response = client.get("/api/benchmarks/judge-suite-v1")
    assert response.status_code == 200
    payload = response.json()
    assert payload["requires_judge"] is True
    assert payload["requires_code_exec"] is False


def test_get_unknown_benchmark_returns_404(api_client):
    client, _settings = api_client
    response = client.get("/api/benchmarks/does-not-exist")
    assert response.status_code == 404
    assert "detail" in response.json()


def test_invalid_benchmark_returns_400(api_client):
    client, settings = api_client
    benchmarks_dir = settings.data_dir / "benchmarks"
    benchmarks_dir.mkdir(parents=True)
    (benchmarks_dir / "broken-suite.yaml").write_text(
        yaml.dump(
            {
                "id": "broken-suite",
                "version": 1,
                "type": "text",
                "tasks": [],
            }
        ),
        encoding="utf-8",
    )

    response = client.get("/api/benchmarks/broken-suite")
    assert response.status_code == 400
    assert "detail" in response.json()


def test_list_runs_empty(api_client):
    client, _settings = api_client
    response = client.get("/api/runs")
    assert response.status_code == 200
    assert response.json() == []


def test_list_and_get_run(seeded_run):
    client, run = seeded_run

    list_response = client.get("/api/runs")
    assert list_response.status_code == 200
    runs = list_response.json()
    assert len(runs) == 1
    assert runs[0]["run_id"] == run.run_id
    assert runs[0]["model"] == "ollama/llama3.1:8b"
    assert runs[0]["benchmark"] == {"id": "text-reasoning-v1", "version": 1}

    detail_response = client.get(f"/api/runs/{run.run_id}")
    assert detail_response.status_code == 200
    payload = detail_response.json()
    assert payload["run"]["run_id"] == run.run_id
    assert payload["run"]["summary"]["mean_score"] == 1.0
    assert len(payload["results"]) == 1
    assert payload["results"][0]["task_id"] == "arithmetic"
    assert payload["results"][0]["output"] == "4"
    assert payload["results"][0]["score"] == 1.0


def test_get_unknown_run_returns_404(api_client):
    client, _settings = api_client
    response = client.get("/api/runs/missing-run")
    assert response.status_code == 404


def test_get_task_output_plain_text(seeded_run):
    client, run = seeded_run
    response = client.get(f"/api/runs/{run.run_id}/results/arithmetic/output")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert response.text == "4"


def test_get_missing_task_output_returns_404(seeded_run):
    client, run = seeded_run
    response = client.get(f"/api/runs/{run.run_id}/results/missing/output")
    assert response.status_code == 404


@patch("elenchos.web.routers.providers.get_provider")
@patch("elenchos.web.routers.providers.list_provider_names")
def test_list_providers(mock_names, mock_get_provider, api_client):
    client, _settings = api_client
    mock_names.return_value = ["ollama", "lmstudio"]
    healthy = MagicMock()
    healthy.base_url = "http://localhost:11434/v1"
    healthy.health_check.return_value = True
    unhealthy = MagicMock()
    unhealthy.base_url = "http://localhost:1234/v1"
    unhealthy.health_check.return_value = False
    mock_get_provider.side_effect = [healthy, unhealthy]

    response = client.get("/api/providers")
    assert response.status_code == 200
    payload = response.json()
    assert payload == [
        {"name": "ollama", "base_url": "http://localhost:11434/v1", "healthy": True},
        {"name": "lmstudio", "base_url": "http://localhost:1234/v1", "healthy": False},
    ]


@patch("elenchos.web.routers.providers.list_provider_names")
def test_list_models_unknown_provider(mock_names, api_client):
    client, _settings = api_client
    mock_names.return_value = ["ollama"]

    response = client.get("/api/providers/missing/models")
    assert response.status_code == 404


@patch("elenchos.web.routers.providers.get_provider")
@patch("elenchos.web.routers.providers.list_provider_names")
def test_list_models_unhealthy_provider(mock_names, mock_get_provider, api_client):
    client, _settings = api_client
    mock_names.return_value = ["ollama"]
    provider = MagicMock()
    provider.name = "ollama"
    provider.base_url = "http://localhost:11434/v1"
    provider.health_check.return_value = False
    mock_get_provider.return_value = provider

    response = client.get("/api/providers/ollama/models")
    assert response.status_code == 502


@patch("elenchos.web.routers.providers.get_provider")
@patch("elenchos.web.routers.providers.list_provider_names")
def test_list_models_returns_models(mock_names, mock_get_provider, api_client):
    client, _settings = api_client
    mock_names.return_value = ["ollama"]
    provider = MagicMock()
    provider.name = "ollama"
    provider.base_url = "http://localhost:11434/v1"
    provider.health_check.return_value = True
    provider.list_models.return_value = ["llama3.1:8b", "mistral:latest"]
    mock_get_provider.return_value = provider

    response = client.get("/api/providers/ollama/models")
    assert response.status_code == 200
    assert response.json() == {"models": ["llama3.1:8b", "mistral:latest"]}


def test_post_run_rejects_code_exec_without_flag(api_client):
    client, _settings = api_client
    response = client.post(
        "/api/runs",
        json={
            "benchmark": "coding-basics-v1",
            "model": "ollama/llama3.1:8b",
        },
    )
    assert response.status_code == 400
    assert "allow-code-exec" in response.json()["detail"].lower()


@patch("elenchos.web.jobs.run_suite")
def test_post_run_enqueues_job(mock_run_suite, api_client):
    client, settings = api_client
    run_dir, run = create_run(
        model="ollama/llama3.1:8b",
        params={"temperature": 0.0, "max_tokens": 1024},
        benchmark=BenchmarkRef(id="text-reasoning-v1", version=1),
        settings=settings,
    )

    def fake_run_suite(
        suite,
        model,
        *,
        settings=None,
        on_event=None,
        **kwargs,
    ):
        if on_event is not None:
            on_event("run_started", {"run_id": run.run_id})
            for index, task in enumerate(suite.tasks, start=1):
                on_event(
                    "task_done",
                    {
                        "task_id": task.id,
                        "index": index,
                        "total": len(suite.tasks),
                        "score": 1.0,
                        "error": None,
                    },
                )
            summary = {"mean_score": 1.0, "pass_rate": 1.0, "task_count": 1}
            on_event("run_finished", {"summary": summary})
        return SuiteRunOutcome(
            run=run,
            run_dir=run_dir,
            results=[],
            summary={"mean_score": 1.0, "pass_rate": 1.0, "task_count": 1},
        )

    mock_run_suite.side_effect = fake_run_suite

    response = client.post(
        "/api/runs",
        json={
            "benchmark": "text-reasoning-v1",
            "model": "ollama/llama3.1:8b",
        },
    )
    assert response.status_code == 202
    payload = response.json()
    assert "job_id" in payload

    job_id = payload["job_id"]
    for _ in range(50):
        job = job_manager.get(job_id)
        if job is not None and job.status == "done":
            break
        time.sleep(0.05)

    job = job_manager.get(job_id)
    assert job is not None
    assert job.status == "done"
    assert job.run_id == run.run_id
    assert job.progress[0].event == "run_started"
    assert job.progress[-1].event == "run_finished"
    assert all(item.event == "task_done" for item in job.progress[1:-1])
    assert len(job.progress) >= 3

    status_response = client.get(f"/api/jobs/{job_id}")
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "done"
    assert status_response.json()["run_id"] == run.run_id


@patch("elenchos.web.routers.runs.get_provider")
def test_post_prompt_persists_run(mock_get_provider, api_client):
    client, settings = api_client
    provider = MagicMock()
    provider.name = "ollama"
    provider.base_url = "http://localhost:11434/v1"
    provider.health_check.return_value = True
    completion = MagicMock()
    completion.text = "hello"
    completion.latency_ms = 120.0
    completion.prompt_tokens = 5
    completion.completion_tokens = 2
    completion.finish_reason = "stop"
    provider.complete.return_value = completion
    mock_get_provider.return_value = provider

    response = client.post(
        "/api/prompt",
        json={"model": "ollama/llama3.1:8b", "text": "Say hello"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["output"] == "hello"
    assert payload["latency_ms"] == 120.0

    run_id = payload["run_id"]
    detail = client.get(f"/api/runs/{run_id}")
    assert detail.status_code == 200
    assert detail.json()["results"][0]["output"] == "hello"


def _seed_compare_run(client_settings, *, suffix: str, output: str):
    client, settings = client_settings
    run_dir, run = create_run(
        model=f"ollama/model-{suffix}",
        params={"temperature": 0.0, "max_tokens": 1024},
        benchmark=BenchmarkRef(id="text-reasoning-v1", version=1),
        settings=settings,
    )
    output_ref = save_output(run_dir, "arithmetic", output)
    append_result(
        run_dir,
        Result(
            task_id="arithmetic",
            prompt="What is 2+2?",
            latency_ms=150.0,
            output_ref=output_ref,
            score=1.0,
            scorer="exact_match",
            finish_reason="stop",
        ),
    )
    run.summary = {"mean_score": 1.0, "pass_rate": 1.0, "p95_latency_ms": 150.0}
    finalize_run(run_dir, run)
    return run


def test_post_compare_pairwise_rejects_three_runs(api_client):
    client, _settings = api_client
    response = client.post(
        "/api/compare",
        json={
            "run_ids": ["a", "b", "c"],
            "mode": "pairwise",
            "judge": "ollama/llama3.1:8b",
        },
    )
    assert response.status_code == 400
    assert "exactly two runs" in response.json()["detail"]


@patch("elenchos.web.jobs.compare_runs")
def test_post_compare_enqueues_job(mock_compare_runs, api_client):
    client, settings = api_client
    run_a = _seed_compare_run((client, settings), suffix="a", output="4")
    run_b = _seed_compare_run((client, settings), suffix="b", output="four")

    artifact_dict = {
        "comparison_id": "abc123",
        "mode": "pairwise",
        "judge_model": "mock/judge",
        "benchmark_id": "text-reasoning-v1",
        "started_at": "2025-01-01T00:00:00+00:00",
        "finished_at": "2025-01-01T00:00:01+00:00",
        "runs": [
            {"run_id": run_a.run_id, "model": run_a.model},
            {"run_id": run_b.run_id, "model": run_b.model},
        ],
        "tasks": [
            {
                "task_id": "arithmetic",
                "prompt": "What is 2+2?",
                "winner_run_id": run_a.run_id,
                "rationale": "A is correct",
                "scores": {},
            }
        ],
        "summary": {
            "task_count": 1,
            "wins": {run_a.run_id: 1, run_b.run_id: 0},
            "ties": 0,
            "win_rate": {run_a.run_id: 1.0, run_b.run_id: 0.0},
        },
    }

    from elenchos.compare import ComparisonArtifact, TaskComparison

    artifact = ComparisonArtifact(
        comparison_id="abc123",
        mode="pairwise",
        judge_model="mock/judge",
        benchmark_id="text-reasoning-v1",
        started_at="2025-01-01T00:00:00+00:00",
        finished_at="2025-01-01T00:00:01+00:00",
        runs=artifact_dict["runs"],
        tasks=[TaskComparison(**artifact_dict["tasks"][0])],
        summary=artifact_dict["summary"],
    )

    def fake_compare_runs(run_ids, *, on_event=None, **kwargs):
        if on_event is not None:
            on_event("compare_started", {"comparison_id": "abc123", "task_count": 1})
            on_event(
                "task_done",
                {
                    "task_id": "arithmetic",
                    "index": 1,
                    "total": 1,
                    "winner_run_id": run_a.run_id,
                },
            )
            on_event(
                "compare_finished",
                {"comparison_id": "abc123", "summary": artifact.summary},
            )
        from elenchos.storage import save_comparison

        comp_dir = save_comparison(artifact, settings=settings)
        return artifact, comp_dir

    mock_compare_runs.side_effect = fake_compare_runs

    response = client.post(
        "/api/compare",
        json={
            "run_ids": [run_a.run_id, run_b.run_id],
            "mode": "pairwise",
            "judge": "mock/judge",
        },
    )
    assert response.status_code == 202
    job_id = response.json()["job_id"]

    for _ in range(50):
        job = job_manager.get(job_id)
        if job is not None and job.status == "done":
            break
        time.sleep(0.05)

    job = job_manager.get(job_id)
    assert job is not None
    assert job.status == "done"
    assert job.comparison_id == "abc123"
    assert job.progress[0].event == "compare_started"
    assert job.progress[-1].event == "compare_finished"

    list_response = client.get("/api/comparisons")
    assert list_response.status_code == 200
    summaries = list_response.json()
    assert any(item["comparison_id"] == "abc123" for item in summaries)

    detail_response = client.get("/api/comparisons/abc123")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["comparison_id"] == "abc123"
    assert detail["tasks"][0]["winner_run_id"] == run_a.run_id


def test_post_report_json(api_client):
    client, settings = api_client
    run_a = _seed_compare_run((client, settings), suffix="a", output="4")
    run_b = _seed_compare_run((client, settings), suffix="b", output="3")

    response = client.post(
        "/api/report",
        json={"run_ids": [run_a.run_id, run_b.run_id], "format": "json"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["benchmark_id"] == "text-reasoning-v1"
    assert len(payload["runs"]) == 2
    assert payload["runs"][0]["mean_score"] == 1.0


def test_post_report_md(api_client):
    client, settings = api_client
    run_a = _seed_compare_run((client, settings), suffix="a", output="4")

    response = client.post(
        "/api/report",
        json={"run_ids": [run_a.run_id], "format": "md"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert "# Benchmark Report" in response.text
