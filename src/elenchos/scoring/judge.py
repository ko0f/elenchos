"""LLM-based judging: rubric scoring and pairwise comparison."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterator
from dataclasses import dataclass

from elenchos.benchmarks.schema import JudgeRubricScorer
from elenchos.models import build_messages, default_generation_params
from elenchos.providers.base import GenerationParams, Provider
from elenchos.scoring.deterministic import ScoreOutcome

logger = logging.getLogger(__name__)

_JSON_BLOCK_RE = re.compile(
    r"```(?:json)?\s*(\{.*?\})\s*```",
    re.DOTALL | re.IGNORECASE,
)
class JudgeParseError(ValueError):
    """Judge response could not be parsed."""


@dataclass(frozen=True)
class ParsedJudgeResponse:
    score: float | None = None
    max_score: float | None = None
    winner: str | None = None
    rationale: str | None = None


@dataclass(frozen=True)
class JudgeContext:
    provider: Provider
    model: str
    qualified: str
    params: GenerationParams | None = None


def extract_json_object(text: str) -> dict:
    """Parse structured JSON from judge output (raw or fenced)."""
    stripped = text.strip()
    if not stripped:
        raise JudgeParseError("empty judge response")

    try:
        payload = json.loads(stripped)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass

    block_match = _JSON_BLOCK_RE.search(stripped)
    if block_match:
        try:
            payload = json.loads(block_match.group(1))
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            pass

    for candidate in _iter_brace_spans(stripped):
        try:
            payload = json.loads(candidate)
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            continue

    raise JudgeParseError(f"no JSON object found in judge response: {stripped[:200]!r}")


def _iter_brace_spans(text: str) -> Iterator[str]:
    """Yield top-level balanced ``{...}`` spans in order of appearance."""
    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth > 0:
            depth -= 1
            if depth == 0:
                yield text[start : i + 1]


def parse_judge_response(text: str) -> ParsedJudgeResponse:
    """Parse judge JSON into normalized fields."""
    payload = extract_json_object(text)

    score = payload.get("score")
    max_score = payload.get("max")
    winner = payload.get("winner")
    rationale = payload.get("rationale")

    parsed_score = float(score) if score is not None else None
    parsed_max = float(max_score) if max_score is not None else None
    parsed_winner = str(winner).strip().upper() if winner is not None else None
    if parsed_winner == "TIE":
        parsed_winner = "tie"
    elif parsed_winner not in {"A", "B"}:
        parsed_winner = None

    parsed_rationale = str(rationale).strip() if rationale is not None else None

    return ParsedJudgeResponse(
        score=parsed_score,
        max_score=parsed_max,
        winner=parsed_winner,
        rationale=parsed_rationale,
    )


def normalize_rubric_score(parsed: ParsedJudgeResponse) -> float:
    if parsed.score is None:
        raise JudgeParseError("judge rubric response missing score")

    maximum = parsed.max_score if parsed.max_score and parsed.max_score > 0 else 5.0
    normalized = parsed.score / maximum
    return max(0.0, min(1.0, normalized))


def _call_judge(
    judge: JudgeContext,
    user_content: str,
    *,
    params: GenerationParams | None = None,
) -> str:
    completion = judge.provider.complete(
        judge.model,
        build_messages(user_content, system=_JUDGE_SYSTEM),
        params or judge.params or default_generation_params(),
    )
    return completion.text


_JUDGE_SYSTEM = (
    "You are an impartial evaluator. Follow instructions exactly and respond "
    "with a single JSON object only, no other text."
)


def judge_rubric(
    judge: JudgeContext,
    *,
    prompt: str,
    output: str,
    rubric: str,
    params: GenerationParams | None = None,
) -> ScoreOutcome:
    """Score one output against a rubric via the judge model."""
    user_content = (
        "Score the model output against the rubric.\n\n"
        f"Task prompt:\n{prompt}\n\n"
        f"Model output:\n{output}\n\n"
        f"Rubric:\n{rubric}\n\n"
        'Respond with JSON only: {"score": <number>, "max": <number>, '
        '"rationale": "<brief explanation>"}'
    )

    try:
        raw = _call_judge(judge, user_content, params=params)
        parsed = parse_judge_response(raw)
        normalized = normalize_rubric_score(parsed)
    except Exception as exc:
        logger.warning("Judge rubric scoring failed: %s", exc)
        return ScoreOutcome(score=0.0, scorer="judge_rubric", passed=0, total=1)

    passed = 1 if normalized >= 1.0 else 0
    return ScoreOutcome(
        score=normalized,
        scorer="judge_rubric",
        passed=passed,
        total=1,
    )


def _single_pairwise(
    judge: JudgeContext,
    *,
    prompt: str,
    output_a: str,
    output_b: str,
    params: GenerationParams | None = None,
) -> ParsedJudgeResponse:
    user_content = (
        "Compare two model outputs for the same task and pick the better one.\n\n"
        f"Task prompt:\n{prompt}\n\n"
        f"Response A:\n{output_a}\n\n"
        f"Response B:\n{output_b}\n\n"
        'Respond with JSON only: {"winner": "A" | "B" | "tie", '
        '"rationale": "<brief explanation>"}'
    )
    raw = _call_judge(judge, user_content, params=params)
    return parse_judge_response(raw)


def pairwise_winner(
    judge: JudgeContext,
    *,
    prompt: str,
    output_a: str,
    output_b: str,
    params: GenerationParams | None = None,
) -> tuple[str, str | None]:
    """Return winner label A, B, or tie with position-bias mitigation."""
    try:
        first = _single_pairwise(
            judge,
            prompt=prompt,
            output_a=output_a,
            output_b=output_b,
            params=params,
        )
        second = _single_pairwise(
            judge,
            prompt=prompt,
            output_a=output_b,
            output_b=output_a,
            params=params,
        )
    except Exception as exc:
        logger.warning("Judge pairwise comparison failed: %s", exc)
        return "tie", str(exc)

    votes_a = 0
    votes_b = 0
    rationales: list[str] = []

    for parsed, swapped in ((first, False), (second, True)):
        winner = parsed.winner
        if not winner or winner == "tie":
            continue
        label = winner.upper()
        if not swapped:
            if label == "A":
                votes_a += 1
            elif label == "B":
                votes_b += 1
        else:
            if label == "A":
                votes_b += 1
            elif label == "B":
                votes_a += 1
        if parsed.rationale:
            rationales.append(parsed.rationale)

    if votes_a > votes_b:
        final = "A"
    elif votes_b > votes_a:
        final = "B"
    else:
        final = "tie"

    rationale = " | ".join(rationales) if rationales else None
    return final, rationale


def score_judge_rubric(
    output: str,
    scorer: JudgeRubricScorer,
    *,
    prompt: str,
    judge: JudgeContext,
) -> ScoreOutcome:
    return judge_rubric(
        judge,
        prompt=prompt,
        output=output,
        rubric=scorer.rubric,
    )
