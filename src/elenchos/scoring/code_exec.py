"""Sandboxed execution for unit_test scoring."""

from __future__ import annotations

import logging
import os
import re
import signal
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

from elenchos.benchmarks.schema import UnitTestScorer
from elenchos.scoring.deterministic import ScoreOutcome

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SEC = 10.0
DEFAULT_MEMORY_BYTES = 256 * 1024 * 1024

_CODE_BLOCK_RE = re.compile(
    r"```(?:python)?\s*\n(.*?)```",
    re.DOTALL | re.IGNORECASE,
)


class CodeExecRefusedError(PermissionError):
    """Code execution was not enabled."""


def extract_code_block(output: str, *, language: str = "python") -> str:
    """Extract a fenced code block from model output, or return stripped text."""
    if language == "python":
        match = _CODE_BLOCK_RE.search(output)
        if match:
            return match.group(1).strip()

    generic = re.search(r"```\w*\s*\n(.*?)```", output, re.DOTALL)
    if generic:
        return generic.group(1).strip()

    return output.strip()


def _parse_test_lines(tests: str) -> list[str]:
    return [
        line.strip()
        for line in tests.strip().splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


_RUNNER_SCRIPT = textwrap.dedent(
    f"""\
    import sys
    import traceback

    DEFAULT_MEMORY_BYTES = {DEFAULT_MEMORY_BYTES}
    DEFAULT_TIMEOUT_SEC = {DEFAULT_TIMEOUT_SEC}


    def _apply_resource_limits() -> None:
        try:
            import resource
        except ImportError:
            return

        try:
            resource.setrlimit(
                resource.RLIMIT_AS,
                (DEFAULT_MEMORY_BYTES, DEFAULT_MEMORY_BYTES),
            )
        except (OSError, ValueError):
            pass
        try:
            cpu_limit = int(DEFAULT_TIMEOUT_SEC)
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_limit, cpu_limit))
        except (OSError, ValueError):
            pass


    def main() -> int:
        _apply_resource_limits()

        solution_path = sys.argv[1]
        tests_path = sys.argv[2]

        with open(solution_path, encoding="utf-8") as handle:
            solution_code = handle.read()

        namespace: dict = {{"__name__": "solution"}}
        try:
            exec(compile(solution_code, solution_path, "exec"), namespace)
        except Exception:
            traceback.print_exc()
            test_lines = _read_tests(tests_path)
            print("ELENCHOS_PASSED=0")
            print(f"ELENCHOS_TOTAL={{len(test_lines)}}")
            return 1

        test_lines = _read_tests(tests_path)
        passed = 0
        for line in test_lines:
            try:
                exec(line, namespace)
                passed += 1
            except AssertionError:
                pass
            except Exception:
                pass

        print(f"ELENCHOS_PASSED={{passed}}")
        print(f"ELENCHOS_TOTAL={{len(test_lines)}}")
        return 0


    def _read_tests(path: str) -> list[str]:
        with open(path, encoding="utf-8") as handle:
            return [
                line.strip()
                for line in handle.readlines()
                if line.strip() and not line.strip().startswith("#")
            ]


    if __name__ == "__main__":
        sys.exit(main())
    """
).strip()


def run_unit_tests(
    output: str,
    scorer: UnitTestScorer,
    *,
    allow_code_exec: bool = False,
    timeout: float = DEFAULT_TIMEOUT_SEC,
) -> ScoreOutcome:
    """Execute model code against assert-based tests in a sandboxed subprocess."""
    if not allow_code_exec:
        raise CodeExecRefusedError(
            "unit_test scoring requires --allow-code-exec "
            "(executes untrusted model-generated code)."
        )

    if scorer.language != "python":
        raise ValueError(f"Unsupported language: {scorer.language!r}")

    test_lines = _parse_test_lines(scorer.tests)
    total = len(test_lines)

    code = extract_code_block(output)
    if not code:
        return ScoreOutcome(score=0.0, scorer=scorer.type, passed=0, total=total)

    passed, timed_out = _execute_in_sandbox(code, scorer.tests, timeout=timeout)
    if timed_out:
        return ScoreOutcome(score=0.0, scorer=scorer.type, passed=0, total=total)

    score = passed / total if total else 1.0
    return ScoreOutcome(
        score=score,
        scorer=scorer.type,
        passed=passed,
        total=total,
    )


def _execute_in_sandbox(
    code: str,
    tests: str,
    *,
    timeout: float,
) -> tuple[int, bool]:
    """Run solution + tests in a subprocess; return (passed, timed_out)."""
    with tempfile.TemporaryDirectory(prefix="elenchos-sandbox-") as tmpdir:
        tmp = Path(tmpdir)
        solution_path = tmp / "solution.py"
        tests_path = tmp / "tests.txt"
        runner_path = tmp / "runner.py"

        solution_path.write_text(code, encoding="utf-8")
        tests_path.write_text(tests, encoding="utf-8")
        runner_path.write_text(_RUNNER_SCRIPT, encoding="utf-8")

        cmd = [sys.executable, str(runner_path), str(solution_path), str(tests_path)]
        popen_kwargs: dict = {
            "cwd": tmpdir,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
        }
        if hasattr(os, "setsid"):
            popen_kwargs["start_new_session"] = True

        proc = subprocess.Popen(cmd, **popen_kwargs)
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill_process_group(proc)
            proc.wait()
            logger.debug("Sandbox timed out after %.1fs", timeout)
            return 0, True

        if stderr:
            logger.debug("Sandbox stderr: %s", stderr.strip())

        if "ELENCHOS_PASSED=" not in (stdout or ""):
            return 0, False

        return _parse_passed(stdout or ""), False


def _kill_process_group(proc: subprocess.Popen) -> None:
    if hasattr(os, "setsid"):
        try:
            os.killpg(proc.pid, signal.SIGKILL)
            return
        except ProcessLookupError:
            pass
    proc.kill()


def _parse_passed(stdout: str) -> int:
    for line in stdout.splitlines():
        if line.startswith("ELENCHOS_PASSED="):
            return int(line.split("=", 1)[1])
    return 0
