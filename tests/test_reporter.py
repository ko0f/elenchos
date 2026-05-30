from __future__ import annotations

from pathlib import Path

import pytest

from elenchos.metrics import aggregate_run_summary
from elenchos.models import BenchmarkRef, Result
from elenchos.reporter import (
    ReportError,
    build_leaderboard,
    format_report,
    format_report_csv,
    format_report_json,
)
from elenchos.storage import append_result, create_run, finalize_run, save_output


def _seed_scored_run(
    tmp_path: Path,
    *,
    suffix: str,
    scores: dict[str, float],
    benchmark_id: str = "tiny-text",
) -> str:
    from elenchos.config import ElenchosSettings

    settings = ElenchosSettings(data_dir=tmp_path)
    run_dir, run = create_run(
        model=f"mock/model-{suffix}",
        params={"temperature": 0.0},
        benchmark=BenchmarkRef(id=benchmark_id, version=1),
        settings=settings,
    )
    results = []
    for task_id, score in scores.items():
        output_ref = save_output(run_dir, task_id, f"output-{task_id}")
        result = Result(
            task_id=task_id,
            latency_ms=100.0,
            score=score,
            output_ref=output_ref,
        )
        append_result(run_dir, result)
        results.append(result)

    run.summary = aggregate_run_summary(results)
    finalize_run(run_dir, run)
    return run.run_id


def test_build_leaderboard_ranks_by_mean_score(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ELENCHOS_DATA_DIR", str(tmp_path))
    run_a = _seed_scored_run(tmp_path, suffix="a", scores={"t1": 1.0, "t2": 1.0})
    run_b = _seed_scored_run(tmp_path, suffix="b", scores={"t1": 0.5, "t2": 0.5})
    run_c = _seed_scored_run(tmp_path, suffix="c", scores={"t1": 0.0, "t2": 1.0})

    report = build_leaderboard([run_b, run_a, run_c])

    assert report.benchmark_id == "tiny-text"
    assert [row.run_id for row in report.rows] == [run_a, run_b, run_c]
    assert report.rows[0].rank == 1
    assert report.rows[0].mean_score == 1.0
    assert report.rows[1].mean_score == 0.5
    assert report.rows[1].rank == 2
    assert report.rows[2].mean_score == 0.5
    assert report.rows[2].rank == 3
    assert report.rows[0].pass_rate == 1.0
    assert report.rows[2].pass_rate == 0.5


def test_build_leaderboard_rejects_mixed_benchmarks(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ELENCHOS_DATA_DIR", str(tmp_path))
    run_a = _seed_scored_run(
        tmp_path,
        suffix="a",
        scores={"t1": 1.0},
        benchmark_id="bench-a",
    )
    run_b = _seed_scored_run(
        tmp_path,
        suffix="b",
        scores={"t1": 1.0},
        benchmark_id="bench-b",
    )

    with pytest.raises(ReportError, match="same benchmark"):
        build_leaderboard([run_a, run_b])


def test_format_report_matches_fixture(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ELENCHOS_DATA_DIR", str(tmp_path))
    run_a = _seed_scored_run(tmp_path, suffix="a", scores={"t1": 1.0, "t2": 0.5})
    run_b = _seed_scored_run(tmp_path, suffix="b", scores={"t1": 0.0, "t2": 0.0})

    report = build_leaderboard([run_a, run_b])
    payload = format_report_json(report)
    assert '"benchmark_id": "tiny-text"' in payload
    assert '"mean_score": 0.75' in payload

    csv_text = format_report_csv(report)
    assert "rank,run_id,model,mean_score" in csv_text
    assert run_a in csv_text

    md_text = format_report(report, "md")
    assert "# Benchmark Report" in md_text
    assert "mock/model-a" in md_text


def test_build_leaderboard_includes_win_rate(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ELENCHOS_DATA_DIR", str(tmp_path))
    run_a = _seed_scored_run(tmp_path, suffix="a", scores={"t1": 1.0})
    run_b = _seed_scored_run(tmp_path, suffix="b", scores={"t1": 0.0})

    report = build_leaderboard(
        [run_a, run_b],
        win_rates={run_a: 0.75, run_b: 0.25},
    )

    by_id = {row.run_id: row for row in report.rows}
    assert by_id[run_a].win_rate == 0.75
    assert by_id[run_b].win_rate == 0.25

    md_text = format_report(report, "md")
    assert "Win Rate" in md_text
