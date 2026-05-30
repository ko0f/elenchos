"""Deterministic text scorers (no LLM)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from elenchos.benchmarks.schema import (
    ContainsAllScorer,
    ExactMatchScorer,
    MetricsScorer,
    RegexMatchScorer,
    ScorerConfig,
    UnitTestScorer,
)


@dataclass(frozen=True)
class ScoreOutcome:
    score: float | None
    scorer: str | None
    passed: int | None = None
    total: int | None = None


UNSUPPORTED_SCORERS = frozenset({"judge_rubric"})


def normalize_output(text: str) -> str:
    return text.strip()


def exact_match(output: str, expected: str) -> float:
    return 1.0 if normalize_output(output) == expected.strip() else 0.0


def regex_match(output: str, pattern: str) -> float:
    return 1.0 if re.search(pattern, output, flags=re.MULTILINE) else 0.0


def contains_all(output: str, strings: list[str]) -> float:
    if not strings:
        return 1.0
    haystack = output
    matched = sum(1 for needle in strings if needle in haystack)
    return matched / len(strings)


def score_with_scorer(
    output: str,
    scorer: ScorerConfig,
    *,
    allow_code_exec: bool = False,
) -> ScoreOutcome:
    if isinstance(scorer, MetricsScorer):
        return ScoreOutcome(score=None, scorer="metrics")

    if scorer.type in UNSUPPORTED_SCORERS:
        raise ValueError(
            f"Scorer {scorer.type!r} is not supported in this release "
            "(requires a judge model)."
        )

    if isinstance(scorer, UnitTestScorer):
        from elenchos.scoring.code_exec import run_unit_tests

        return run_unit_tests(
            output,
            scorer,
            allow_code_exec=allow_code_exec,
        )

    if isinstance(scorer, ExactMatchScorer):
        score = exact_match(output, scorer.expected)
        return ScoreOutcome(
            score=score,
            scorer=scorer.type,
            passed=int(score >= 1.0),
            total=1,
        )

    if isinstance(scorer, RegexMatchScorer):
        score = regex_match(output, scorer.pattern)
        return ScoreOutcome(
            score=score,
            scorer=scorer.type,
            passed=int(score >= 1.0),
            total=1,
        )

    if isinstance(scorer, ContainsAllScorer):
        matched = sum(1 for needle in scorer.strings if needle in output)
        total = len(scorer.strings)
        score = matched / total if total else 1.0
        return ScoreOutcome(
            score=score,
            scorer=scorer.type,
            passed=matched,
            total=total,
        )

    raise ValueError(f"Unknown scorer type: {scorer.type!r}")


def score_task_output(
    output: str,
    scorers: list[ScorerConfig],
    *,
    allow_code_exec: bool = False,
) -> ScoreOutcome:
    """Score model output against all configured scorers (metrics excluded)."""
    outcomes = [
        score_with_scorer(output, scorer, allow_code_exec=allow_code_exec)
        for scorer in scorers
    ]
    graded = [outcome for outcome in outcomes if outcome.score is not None]

    if not graded:
        return ScoreOutcome(score=None, scorer=None)

    if len(graded) == 1:
        return graded[0]

    mean_score = sum(outcome.score for outcome in graded) / len(graded)
    passed = sum(outcome.passed or 0 for outcome in graded)
    total = sum(outcome.total or 0 for outcome in graded)
    scorer = "+".join(outcome.scorer for outcome in graded if outcome.scorer)
    return ScoreOutcome(
        score=mean_score,
        scorer=scorer,
        passed=passed,
        total=total,
    )
