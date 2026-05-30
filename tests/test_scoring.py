import pytest

from elenchos.benchmarks.schema import (
    ContainsAllScorer,
    ExactMatchScorer,
    MetricsScorer,
)
from elenchos.scoring.deterministic import (
    contains_all,
    exact_match,
    regex_match,
    score_task_output,
)


@pytest.mark.parametrize(
    ("output", "expected", "score"),
    [
        ("4", "4", 1.0),
        ("  4 \n", "4", 1.0),
        ("four", "4", 0.0),
    ],
)
def test_exact_match(output: str, expected: str, score: float):
    assert exact_match(output, expected) == score


@pytest.mark.parametrize(
    ("output", "pattern", "score"),
    [
        ("yes", "(?i)^yes\\.?$", 1.0),
        ("Yes.", "(?i)^yes\\.?$", 1.0),
        ("no", "(?i)^yes\\.?$", 0.0),
    ],
)
def test_regex_match(output: str, pattern: str, score: float):
    assert regex_match(output, pattern) == score


@pytest.mark.parametrize(
    ("output", "strings", "score"),
    [
        ("Paris is nice", ["Paris"], 1.0),
        ("paris", ["Paris"], 0.0),
        ("The Eiffel Tower is in Paris", ["Paris", "France"], 0.5),
    ],
)
def test_contains_all(output: str, strings: list[str], score: float):
    assert contains_all(output, strings) == score


def test_score_task_output_combines_scorers():
    outcome = score_task_output(
        "Paris, France",
        [
            ContainsAllScorer(type="contains_all", strings=["Paris"]),
            ExactMatchScorer(type="exact_match", expected="Paris, France"),
        ],
    )
    assert outcome.score == 1.0
    assert outcome.scorer == "contains_all+exact_match"


def test_score_task_output_ignores_metrics():
    outcome = score_task_output(
        "4",
        [
            ExactMatchScorer(type="exact_match", expected="4"),
            MetricsScorer(type="metrics"),
        ],
    )
    assert outcome.score == 1.0
    assert outcome.scorer == "exact_match"
