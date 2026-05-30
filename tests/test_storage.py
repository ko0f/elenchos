import json

import pytest

from elenchos.models import BenchmarkRef, Result, Run
from elenchos.storage import (
    DEFAULT_TASK_ID,
    append_result,
    create_run,
    finalize_run,
    find_run,
    list_runs,
    load_results,
    read_output,
    save_output,
)


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("ELENCHOS_DATA_DIR", str(tmp_path))
    return tmp_path


def test_storage_round_trip(data_dir):
    run_dir, run = create_run(
        model="ollama/llama3.1:8b",
        params={"temperature": 0.0, "max_tokens": 1024},
        benchmark=BenchmarkRef(id="prompt"),
    )

    output_ref = save_output(run_dir, DEFAULT_TASK_ID, "4")
    append_result(
        run_dir,
        Result(
            task_id=DEFAULT_TASK_ID,
            prompt="2+2?",
            latency_ms=123.4,
            prompt_tokens=5,
            completion_tokens=1,
            output_ref=output_ref,
            finish_reason="stop",
        ),
    )
    finalize_run(run_dir, run)

    stored_run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert stored_run["run_id"] == run.run_id
    assert stored_run["model"] == "ollama/llama3.1:8b"
    assert stored_run["finished_at"]

    results = load_results(run_dir)
    assert len(results) == 1
    assert results[0].prompt == "2+2?"
    assert results[0].output == "4"
    assert results[0].latency_ms == 123.4
    assert read_output(run_dir, output_ref) == "4"


def test_list_and_find_run(data_dir):
    run_dir, run = create_run(
        model="ollama/llama3.1:8b",
        params={"temperature": 0.0},
    )
    finalize_run(run_dir, run)

    runs = list_runs()
    assert len(runs) == 1
    assert runs[0].run_id == run.run_id

    found = find_run(run.run_id)
    assert found is not None
    found_dir, found_run = found
    assert found_dir == run_dir
    assert found_run.model == "ollama/llama3.1:8b"


def test_run_from_dict_round_trip():
    run = Run(
        run_id="abc123",
        started_at="2026-05-30T14:03:12+00:00",
        finished_at="2026-05-30T14:05:40+00:00",
        benchmark=BenchmarkRef(id="prompt", version=1),
        model="ollama/llama3.1:8b",
        params={"temperature": 0.0, "max_tokens": 1024},
        tool_version="0.1.0",
    )
    restored = Run.from_dict(run.to_dict())
    assert restored == run


def test_result_from_dict_round_trip():
    result = Result(
        task_id="prompt",
        prompt="Hello",
        latency_ms=50.0,
        completion_tokens=3,
        output_ref="outputs/prompt.txt",
        finish_reason="stop",
    )
    restored = Result.from_dict(result.to_dict())
    assert restored == result
