from typer.testing import CliRunner

from elenchos.cli import app
from elenchos.models import Result
from elenchos.storage import append_result, create_run, finalize_run, save_output

runner = CliRunner()


def _cli(*args: str) -> list[str]:
    return list(args)


def test_list_empty(tmp_path):
    result = runner.invoke(app, _cli("--data-dir", str(tmp_path), "list"))
    assert result.exit_code == 0
    assert "No runs yet" in result.stdout


def test_list_and_show_known_run(tmp_path):
    run_dir, run = create_run(
        model="ollama/llama3.1:8b",
        params={"temperature": 0.0, "max_tokens": 1024},
    )
    output_ref = save_output(run_dir, "prompt", "four")
    append_result(
        run_dir,
        Result(
            task_id="prompt",
            prompt="2+2?",
            latency_ms=100.0,
            prompt_tokens=4,
            completion_tokens=1,
            output_ref=output_ref,
            finish_reason="stop",
        ),
    )
    finalize_run(run_dir, run)

    list_result = runner.invoke(app, _cli("--data-dir", str(tmp_path), "list"))
    assert list_result.exit_code == 0
    assert run.run_id in list_result.stdout
    assert "ollama/llama3.1:8b" in list_result.stdout
    assert "prompt" in list_result.stdout

    show_result = runner.invoke(app, _cli("--data-dir", str(tmp_path), "show", run.run_id))
    assert show_result.exit_code == 0
    assert "2+2?" in show_result.stdout
    assert "four" in show_result.stdout
    assert "100 ms" in show_result.stdout
    assert "Prompt tokens" in show_result.stdout


def test_show_missing_run(tmp_path):
    result = runner.invoke(app, _cli("--data-dir", str(tmp_path), "show", "missing"))
    assert result.exit_code == 1
    assert "not found" in result.stdout.lower()
