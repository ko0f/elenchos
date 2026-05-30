from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from elenchos.compare import CompareError, compare_runs
from elenchos.config import ElenchosSettings, resolve_judge_config
from elenchos.models import BenchmarkRef, Result
from elenchos.providers.base import Completion, GenerationParams, Message
from elenchos.scoring.judge import JudgeContext
from elenchos.storage import append_result, create_run, finalize_run, save_output


@dataclass
class MockJudgeProvider:
    name: str = "mock"
    base_url: str = "http://mock.test/v1"
    responses: list[str] = field(default_factory=list)
    call_index: int = 0

    def list_models(self) -> list[str]:
        return ["judge"]

    def health_check(self) -> bool:
        return True

    def complete(
        self,
        model: str,
        messages: list[Message],
        params: GenerationParams,
    ) -> Completion:
        text = (
            self.responses[self.call_index]
            if self.call_index < len(self.responses)
            else '{"winner": "A", "rationale": "default"}'
        )
        self.call_index += 1
        return Completion(
            text=text,
            prompt_tokens=1,
            completion_tokens=1,
            latency_ms=1.0,
            raw={},
            finish_reason="stop",
        )


def _seed_run(
    tmp_path: Path,
    *,
    suffix: str,
    output: str,
    task_id: str = "math",
) -> str:
    settings = ElenchosSettings(data_dir=tmp_path)
    run_dir, run = create_run(
        model=f"mock/model-{suffix}",
        params={"temperature": 0.0},
        benchmark=BenchmarkRef(id="tiny-text", version=1),
        settings=settings,
    )
    output_ref = save_output(run_dir, task_id, output)
    append_result(
        run_dir,
        Result(
            task_id=task_id,
            prompt="What is 1+1?",
            latency_ms=10.0,
            output_ref=output_ref,
        ),
    )
    finalize_run(run_dir, run)
    return run.run_id


def test_resolve_judge_config_precedence(tmp_path: Path):
    (tmp_path / "config.yaml").write_text(
        "judge:\n  model: ollama/from-file\n  mode: rubric\n",
        encoding="utf-8",
    )
    settings = ElenchosSettings(data_dir=tmp_path)
    from_file = resolve_judge_config(settings=settings)
    assert from_file.model == "ollama/from-file"
    assert from_file.mode == "rubric"

    cli = resolve_judge_config(
        settings=settings,
        cli_judge="mock/cli-judge",
        cli_mode="pairwise",
    )
    assert cli.model == "mock/cli-judge"
    assert cli.mode == "pairwise"


def test_compare_pairwise_writes_artifact(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ELENCHOS_DATA_DIR", str(tmp_path))
    (tmp_path / "config.yaml").write_text(
        "judge:\n  model: mock/judge\n  mode: pairwise\n",
        encoding="utf-8",
    )

    run_a = _seed_run(tmp_path, suffix="a", output="answer a")
    run_b = _seed_run(tmp_path, suffix="b", output="answer b")

    provider = MockJudgeProvider(
        responses=[
            '{"winner": "A", "rationale": "order1"}',
            '{"winner": "B", "rationale": "order2"}',
        ]
    )
    judge = JudgeContext(provider=provider, model="judge", qualified="mock/judge")

    monkeypatch.setattr(
        "elenchos.compare._build_judge_context",
        lambda *_args, **_kwargs: judge,
    )

    artifact, comp_dir = compare_runs([run_a, run_b])

    assert artifact.mode == "pairwise"
    assert len(artifact.tasks) == 1
    assert artifact.tasks[0].winner_run_id == run_a
    assert comp_dir is not None
    assert (comp_dir / "comparison.json").is_file()
    assert artifact.summary["win_rate"][run_a] == 1.0


def test_compare_rubric_listwise_winner(tmp_path: Path, monkeypatch):
    import random

    monkeypatch.setenv("ELENCHOS_DATA_DIR", str(tmp_path))
    (tmp_path / "config.yaml").write_text(
        "judge:\n  model: mock/judge\n  mode: rubric\n",
        encoding="utf-8",
    )
    bench_dir = tmp_path / "benchmarks"
    bench_dir.mkdir()
    (bench_dir / "tiny-text.yaml").write_text(
        "id: tiny-text\nversion: 1\ntype: text\ntasks:\n"
        "  - id: math\n    prompt: 'What is 1+1?'\n"
        "    scoring:\n      - type: regex_match\n        pattern: '2'\n",
        encoding="utf-8",
    )

    run_a = _seed_run(tmp_path, suffix="a", output="answer a")
    run_b = _seed_run(tmp_path, suffix="b", output="answer b")

    # The output order is shuffled by task_id; replicate it so we know which
    # run id ends up as listwise output 1 (and thus gets the high score).
    order = [run_a, run_b]
    random.Random("math").shuffle(order)

    provider = MockJudgeProvider(
        responses=[
            '{"scores": [{"id": 1, "score": 9, "rationale": "strong"}, '
            '{"id": 2, "score": 2, "rationale": "weak"}]}'
        ]
    )
    judge = JudgeContext(provider=provider, model="judge", qualified="mock/judge")
    monkeypatch.setattr(
        "elenchos.compare._build_judge_context",
        lambda *_args, **_kwargs: judge,
    )

    artifact, _ = compare_runs([run_a, run_b])

    assert artifact.mode == "rubric"
    assert provider.call_index == 1  # one listwise call for the single task
    assert artifact.tasks[0].winner_run_id == order[0]
    assert artifact.tasks[0].scores[order[0]] == pytest.approx(0.9)
    assert artifact.tasks[0].scores[order[1]] == pytest.approx(0.2)


def test_compare_requires_same_benchmark(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ELENCHOS_DATA_DIR", str(tmp_path))
    (tmp_path / "config.yaml").write_text(
        "judge:\n  model: mock/judge\n",
        encoding="utf-8",
    )

    settings = ElenchosSettings(data_dir=tmp_path)
    run_dir, run = create_run(
        model="mock/a",
        params={},
        benchmark=BenchmarkRef(id="suite-a", version=1),
        settings=settings,
    )
    append_result(
        run_dir,
        Result(task_id="t", latency_ms=1.0, output_ref=save_output(run_dir, "t", "x")),
    )
    finalize_run(run_dir, run)
    run_a = run.run_id

    run_dir_b, run_b_meta = create_run(
        model="mock/b",
        params={},
        benchmark=BenchmarkRef(id="suite-b", version=1),
        settings=settings,
    )
    append_result(
        run_dir_b,
        Result(
            task_id="t",
            latency_ms=1.0,
            output_ref=save_output(run_dir_b, "t", "y"),
        ),
    )
    finalize_run(run_dir_b, run_b_meta)
    run_b = run_b_meta.run_id

    with pytest.raises(CompareError, match="same benchmark"):
        compare_runs([run_a, run_b], judge_model="mock/judge")


def test_judge_generation_params_effort():
    from elenchos.models import judge_generation_params

    params = judge_generation_params(reasoning_effort="high")
    assert params.reasoning_effort == "high"

    default = judge_generation_params()
    assert default.reasoning_effort is None


def test_build_judge_context_includes_effort(monkeypatch):
    from elenchos.compare import _build_judge_context

    provider = MockJudgeProvider()
    monkeypatch.setattr(
        "elenchos.compare.get_provider",
        lambda _name, *, settings=None: provider,
    )

    ctx = _build_judge_context("mock/judge", reasoning_effort="medium")
    assert ctx.params is not None
    assert ctx.params.reasoning_effort == "medium"


def test_build_judge_context_requires_openrouter_api_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    from elenchos.compare import CompareError, _build_judge_context

    monkeypatch.setenv("ELENCHOS_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("ELENCHOS_OPENROUTER_API_KEY", raising=False)

    with pytest.raises(CompareError, match="requires an API key"):
        _build_judge_context("openrouter/anthropic/claude-opus-4.8")


def test_compare_cli_pairwise(tmp_path: Path, monkeypatch):
    from typer.testing import CliRunner

    from elenchos.cli import app

    monkeypatch.setenv("ELENCHOS_DATA_DIR", str(tmp_path))
    (tmp_path / "config.yaml").write_text(
        "judge:\n  model: mock/judge\n  mode: pairwise\n",
        encoding="utf-8",
    )

    run_a = _seed_run(tmp_path, suffix="a", output="a")
    run_b = _seed_run(tmp_path, suffix="b", output="b")

    provider = MockJudgeProvider(
        responses=[
            '{"winner": "A", "rationale": "a"}',
            '{"winner": "B", "rationale": "b"}',
        ]
    )
    judge = JudgeContext(provider=provider, model="judge", qualified="mock/judge")
    monkeypatch.setattr(
        "elenchos.compare._build_judge_context",
        lambda *_args, **_kwargs: judge,
    )

    result = CliRunner().invoke(app, ["compare", run_a, run_b])
    assert result.exit_code == 0
    assert "Win rate" in result.stdout
    assert run_a in result.stdout or "model-a" in result.stdout
