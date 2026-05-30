from pathlib import Path

import yaml
from typer.testing import CliRunner

from elenchos.cli import app

runner = CliRunner()


def test_bench_list_includes_builtin():
    result = runner.invoke(app, ["bench", "list"])
    assert result.exit_code == 0
    assert "text-reasoning-v1" in result.stdout
    assert "text" in result.stdout


def test_bench_show_known_suite():
    result = runner.invoke(app, ["bench", "show", "text-reasoning-v1"])
    assert result.exit_code == 0
    assert "text-reasoning-v1" in result.stdout
    assert "arithmetic" in result.stdout
    assert "2+2" in result.stdout


def test_bench_show_malformed_yaml(tmp_path: Path):
    broken = tmp_path / "broken.yaml"
    broken.write_text(
        yaml.dump(
            {
                "id": "broken",
                "version": 1,
                "type": "text",
                "tasks": [{"id": "a", "prompt": "hi", "scoring": [{"type": "bad"}]}],
            }
        ),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["bench", "show", str(broken)])
    assert result.exit_code == 1
    assert "validation failed" in result.stdout.lower()


def test_bench_show_with_benchmark_file(tmp_path: Path):
    suite = tmp_path / "custom.yaml"
    suite.write_text(
        "id: custom\n"
        "version: 1\n"
        "type: text\n"
        "description: From file flag\n"
        "tasks:\n"
        "  - id: one\n"
        "    prompt: Hello\n"
        "    scoring:\n"
        "      - type: exact_match\n"
        "        expected: hello\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        ["bench", "show", "ignored", "--benchmark-file", str(suite)],
    )
    assert result.exit_code == 0
    assert "custom" in result.stdout
    assert "From file flag" in result.stdout
