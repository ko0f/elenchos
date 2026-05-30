import pytest

from elenchos.benchmarks.schema import UnitTestScorer
from elenchos.scoring.code_exec import (
    CodeExecRefusedError,
    extract_code_block,
    run_unit_tests,
)

FIZZBUZZ_GOOD = """\
def fizzbuzz(n):
    if n % 15 == 0:
        return "FizzBuzz"
    if n % 3 == 0:
        return "Fizz"
    if n % 5 == 0:
        return "Buzz"
    return str(n)
"""

FIZZBUZZ_TESTS = """\
assert fizzbuzz(3) == "Fizz"
assert fizzbuzz(5) == "Buzz"
assert fizzbuzz(15) == "FizzBuzz"
assert fizzbuzz(2) == "2"
"""

FIZZBUZZ_BAD = """\
def fizzbuzz(n):
    return "nope"
"""


def _unit_test_scorer(tests: str = FIZZBUZZ_TESTS) -> UnitTestScorer:
    return UnitTestScorer(
        type="unit_test",
        language="python",
        entrypoint="fizzbuzz",
        tests=tests,
    )


def test_extract_code_block_from_markdown():
    output = "Here is the code:\n```python\n" + FIZZBUZZ_GOOD + "\n```"
    assert extract_code_block(output).strip() == FIZZBUZZ_GOOD.strip()


def test_extract_code_block_falls_back_to_raw_text():
    assert extract_code_block(FIZZBUZZ_GOOD).strip() == FIZZBUZZ_GOOD.strip()


def test_run_unit_tests_passes_good_code():
    outcome = run_unit_tests(
        FIZZBUZZ_GOOD,
        _unit_test_scorer(),
        allow_code_exec=True,
    )
    assert outcome.score == 1.0
    assert outcome.passed == 4
    assert outcome.total == 4


def test_run_unit_tests_fails_broken_code():
    outcome = run_unit_tests(
        FIZZBUZZ_BAD,
        _unit_test_scorer(),
        allow_code_exec=True,
    )
    assert outcome.score == 0.0
    assert outcome.passed == 0
    assert outcome.total == 4


def test_run_unit_tests_times_out_infinite_loop():
    outcome = run_unit_tests(
        "while True:\n    pass\n",
        _unit_test_scorer(),
        allow_code_exec=True,
        timeout=1.0,
    )
    assert outcome.score == 0.0
    assert outcome.passed == 0
    assert outcome.total == 4


def test_run_unit_tests_refused_without_flag():
    with pytest.raises(CodeExecRefusedError, match="allow-code-exec"):
        run_unit_tests(FIZZBUZZ_GOOD, _unit_test_scorer(), allow_code_exec=False)


def test_run_unit_tests_empty_output_scores_zero():
    outcome = run_unit_tests(
        "   ",
        _unit_test_scorer(),
        allow_code_exec=True,
    )
    assert outcome.score == 0.0
    assert outcome.passed == 0
    assert outcome.total == 4
