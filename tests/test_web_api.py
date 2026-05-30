from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from fastapi.testclient import TestClient

from elenchos.config import ElenchosSettings
from elenchos.models import BenchmarkRef, Result
from elenchos.storage import (
    append_result,
    create_run,
    finalize_run,
    save_output,
)
from elenchos.web.app import create_app
from elenchos.web.deps import get_settings


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
