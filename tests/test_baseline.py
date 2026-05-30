import pytest

from elenchos.baseline import compute_baseline_comparison, get_or_compute_baseline_comparison
from elenchos.models import BenchmarkRef, Result
from elenchos.storage import (
    append_result,
    create_run,
    finalize_run,
    read_baseline_score,
    save_output,
    set_baseline,
    write_baseline_score,
)


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("ELENCHOS_DATA_DIR", str(tmp_path))
    return tmp_path


def _seed_run(
    *,
    benchmark_id: str = "text-reasoning-v1",
    model: str = "ollama/a",
    task_scores: dict[str, float],
    outputs: dict[str, str] | None = None,
):
    run_dir, run = create_run(
        model=model,
        params={"temperature": 0.0},
        benchmark=BenchmarkRef(id=benchmark_id, version=1),
    )
    for task_id, score in task_scores.items():
        text = (outputs or {}).get(task_id, "out")
        output_ref = save_output(run_dir, task_id, text)
        append_result(
            run_dir,
            Result(
                task_id=task_id,
                prompt="p",
                latency_ms=1.0,
                score=score,
                output_ref=output_ref,
            ),
        )
    finalize_run(run_dir, run)
    return run_dir, run


def test_no_baseline_returns_none(data_dir):
    _run_dir, run = _seed_run(task_scores={"a": 1.0})
    assert compute_baseline_comparison(run.run_id) is None


def test_candidate_is_baseline(data_dir):
    _run_dir, run = _seed_run(task_scores={"a": 1.0})
    set_baseline("text-reasoning-v1", run.run_id)

    comparison = compute_baseline_comparison(run.run_id)
    assert comparison is not None
    assert comparison.is_baseline is True
    assert comparison.relative_score == 1.0
    assert comparison.tasks == []


def test_relative_score_better_worse_parity(data_dir):
    _base_dir, baseline = _seed_run(
        model="ollama/base",
        task_scores={"a": 1.0, "b": 1.0},
    )
    _cand_dir, candidate = _seed_run(
        model="ollama/cand",
        task_scores={"a": 1.0, "b": 1.0},
    )
    set_baseline("text-reasoning-v1", baseline.run_id)

    parity = compute_baseline_comparison(candidate.run_id)
    assert parity is not None
    assert parity.relative_score == pytest.approx(1.0)

    _worse_dir, worse = _seed_run(
        model="ollama/worse",
        task_scores={"a": 0.5, "b": 0.5},
    )
    worse_cmp = compute_baseline_comparison(worse.run_id)
    assert worse_cmp is not None
    assert worse_cmp.relative_score == pytest.approx(0.5)

    _better_dir, better = _seed_run(
        model="ollama/better",
        task_scores={"a": 1.0, "b": 2.0},
    )
    better_cmp = compute_baseline_comparison(better.run_id)
    assert better_cmp is not None
    assert better_cmp.relative_score == pytest.approx(1.5)
    assert len(better_cmp.tasks) == 2
    assert better_cmp.tasks[0].delta == pytest.approx(0.0)
    assert better_cmp.tasks[1].delta == pytest.approx(1.0)


def test_zero_baseline_sum_returns_none(data_dir):
    _base_dir, baseline = _seed_run(task_scores={"a": 0.0})
    _cand_dir, candidate = _seed_run(task_scores={"a": 1.0})
    set_baseline("text-reasoning-v1", baseline.run_id)

    comparison = compute_baseline_comparison(candidate.run_id)
    assert comparison is not None
    assert comparison.relative_score is None


def test_no_shared_tasks_returns_none(data_dir):
    _base_dir, baseline = _seed_run(task_scores={"a": 1.0})
    _cand_dir, candidate = _seed_run(task_scores={"b": 1.0})
    set_baseline("text-reasoning-v1", baseline.run_id)

    comparison = compute_baseline_comparison(candidate.run_id)
    assert comparison is not None
    assert comparison.relative_score is None
    assert comparison.tasks == []


def test_null_cached_score_recomputes_when_tasks_exist(data_dir):
    _base_dir, baseline = _seed_run(task_scores={"a": 1.0})
    _cand_dir, candidate = _seed_run(task_scores={"a": 1.0})
    set_baseline("text-reasoning-v1", baseline.run_id)

    write_baseline_score(
        _cand_dir,
        {
            "baseline_run_id": baseline.run_id,
            "relative_score": None,
            "computed_at": "2020-01-01T00:00:00Z",
            "tasks": [],
        },
    )

    comparison = get_or_compute_baseline_comparison(candidate.run_id)
    assert comparison is not None
    assert comparison.relative_score == pytest.approx(1.0)
    refreshed = read_baseline_score(_cand_dir)
    assert refreshed["relative_score"] == pytest.approx(1.0)


def test_comparison_baseline_uses_rubric_mean(data_dir, monkeypatch):
    from elenchos.storage import save_comparison

    _base_dir, baseline = _seed_run(
        benchmark_id="coding-basics-v1",
        model="ollama/base",
        task_scores={"a": 1.0},
        outputs={"a": "baseline code"},
    )
    _cand_dir, candidate = _seed_run(
        benchmark_id="coding-basics-v1",
        model="ollama/cand",
        task_scores={"a": 1.0},
        outputs={"a": "candidate code"},
    )
    set_baseline("coding-basics-v1", baseline.run_id)

    class _Artifact:
        comparison_id = "cmp-test"
        mode = "rubric"
        benchmark_id = "coding-basics-v1"
        started_at = "2025-01-01T00:00:00+00:00"

        def to_dict(self):
            return {
                "comparison_id": self.comparison_id,
                "mode": self.mode,
                "judge_model": "ollama/judge",
                "benchmark_id": self.benchmark_id,
                "started_at": self.started_at,
                "finished_at": "2025-01-01T00:01:00+00:00",
                "runs": [{"run_id": candidate.run_id, "model": "ollama/cand"}],
                "tasks": [
                    {
                        "task_id": "a",
                        "prompt": "p",
                        "winner_run_id": candidate.run_id,
                        "scores": {candidate.run_id: 0.75},
                    }
                ],
                "summary": {
                    "task_count": 1,
                    "mean_score": {candidate.run_id: 0.75},
                },
            }

    save_comparison(_Artifact(), settings=None)

    comparison = get_or_compute_baseline_comparison(candidate.run_id)
    assert comparison is not None
    assert comparison.relative_score == pytest.approx(0.75)
    assert comparison.tasks[0].score == pytest.approx(0.75)
    assert comparison.score_method == "comparison"

    cached = read_baseline_score(_cand_dir)
    assert cached["method"] == "comparison"
    assert cached["comparison_id"] == "cmp-test"


def test_judge_baseline_for_unit_test_suite(data_dir, monkeypatch):
    from elenchos.benchmarks.registry import resolve_benchmark
    from elenchos.scoring.judge import ListwiseItem

    monkeypatch.setattr(
        "elenchos.baseline.compute_comparison_baseline_comparison",
        lambda *args, **kwargs: None,
    )

    _base_dir, baseline = _seed_run(
        benchmark_id="coding-basics-v1",
        model="ollama/base",
        task_scores={"a": 1.0},
        outputs={"a": "baseline code"},
    )
    _cand_dir, candidate = _seed_run(
        benchmark_id="coding-basics-v1",
        model="ollama/cand",
        task_scores={"a": 1.0},
        outputs={"a": "candidate code"},
    )
    set_baseline("coding-basics-v1", baseline.run_id)

    def fake_listwise(judge, *, prompt, outputs, rubric, strict, context):
        assert outputs[0] == "baseline code"
        assert outputs[1] == "candidate code"
        return [
            ListwiseItem(score=1.0),
            ListwiseItem(score=0.5),
        ]

    monkeypatch.setattr("elenchos.scoring.judge.judge_listwise", fake_listwise)
    monkeypatch.setattr(
        "elenchos.baseline.resolve_judge_config",
        lambda **kwargs: type("Cfg", (), {"model": "ollama/judge", "mode": "rubric"})(),
    )
    monkeypatch.setattr(
        "elenchos.compare._build_judge_context",
        lambda model, **kwargs: object(),
    )
    suite = resolve_benchmark("coding-basics-v1")
    monkeypatch.setattr(
        "elenchos.compare._resolve_rubric",
        lambda s, task_id: ("rubric text", suite.tasks[0]),
    )

    comparison = get_or_compute_baseline_comparison(candidate.run_id)
    assert comparison is not None
    assert comparison.relative_score == pytest.approx(0.5)
    assert comparison.tasks[0].baseline_score == pytest.approx(1.0)
    assert comparison.tasks[0].score == pytest.approx(0.5)

    cached = read_baseline_score(_cand_dir)
    assert cached["method"] == "judge"
    assert comparison.score_method == "judge"
    assert cached["relative_score"] == pytest.approx(0.5)


def test_cache_hit_and_stale_recompute(data_dir):
    _base_dir, baseline = _seed_run(task_scores={"a": 1.0})
    _cand_dir, candidate = _seed_run(task_scores={"a": 0.5})
    set_baseline("text-reasoning-v1", baseline.run_id)

    first = get_or_compute_baseline_comparison(candidate.run_id)
    assert first is not None
    assert first.relative_score == pytest.approx(0.5)
    cached = read_baseline_score(_cand_dir)
    assert cached is not None
    assert cached["relative_score"] == pytest.approx(0.5)

    write_baseline_score(
        _cand_dir,
        {
            "baseline_run_id": baseline.run_id,
            "relative_score": 9.99,
            "computed_at": "2020-01-01T00:00:00Z",
            "tasks": [],
        },
    )
    second = get_or_compute_baseline_comparison(candidate.run_id)
    assert second is not None
    assert second.relative_score == pytest.approx(9.99)

    _other_dir, other_baseline = _seed_run(
        model="ollama/other",
        task_scores={"a": 1.0},
    )
    set_baseline("text-reasoning-v1", other_baseline.run_id)
    third = get_or_compute_baseline_comparison(candidate.run_id)
    assert third is not None
    assert third.baseline_run_id == other_baseline.run_id
    assert third.relative_score == pytest.approx(0.5)
    refreshed = read_baseline_score(_cand_dir)
    assert refreshed["baseline_run_id"] == other_baseline.run_id
