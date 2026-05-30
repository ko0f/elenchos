"""LLM-based judging: rubric scoring and pairwise comparison."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterator
from dataclasses import dataclass

import httpx

from elenchos.benchmarks.schema import JudgeRubricScorer
from elenchos.models import build_messages, default_generation_params
from elenchos.providers.base import Completion, GenerationParams, Provider
from elenchos.scoring.deterministic import ScoreOutcome

logger = logging.getLogger(__name__)

_JSON_BLOCK_RE = re.compile(
    r"```(?:json)?\s*(\{.*?\})\s*```",
    re.DOTALL | re.IGNORECASE,
)
class JudgeParseError(ValueError):
    """Judge response could not be parsed."""


class JudgeProviderError(RuntimeError):
    """Judge LLM call failed (network, auth, model missing, etc.)."""


@dataclass(frozen=True)
class ParsedJudgeResponse:
    score: float | None = None
    max_score: float | None = None
    winner: str | None = None
    rationale: str | None = None


@dataclass(frozen=True)
class ListwiseItem:
    """Relative score (0-1) and rationale for one output in a listwise batch."""

    score: float
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


def _judge_response_text(completion: Completion) -> str:
    """Prefer answer text; fall back to reasoning trace for reasoning models."""
    if completion.text.strip():
        return completion.text
    if completion.reasoning and completion.reasoning.strip():
        logger.debug("Judge answer empty; parsing reasoning_content instead")
        return completion.reasoning
    return completion.text


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
    return _judge_response_text(completion)


def _is_provider_error(exc: BaseException) -> bool:
    return isinstance(
        exc,
        (
            httpx.HTTPError,
            ConnectionError,
            TimeoutError,
            RuntimeError,
        ),
    )


def _handle_judge_failure(
    exc: BaseException,
    *,
    judge: JudgeContext,
    strict: bool,
    context: str,
) -> ScoreOutcome | None:
    if isinstance(exc, JudgeParseError):
        logger.warning(
            "Judge parse failed (%s, model=%s): %s",
            context,
            judge.qualified,
            exc,
        )
        return ScoreOutcome(score=0.0, scorer="judge_rubric", passed=0, total=1)

    if not _is_provider_error(exc):
        raise exc

    message = f"Judge call failed ({context}, model={judge.qualified}): {exc}"
    logger.error(message)
    if strict:
        raise JudgeProviderError(message) from exc
    return ScoreOutcome(score=0.0, scorer="judge_rubric", passed=0, total=1)


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
    strict: bool = False,
    context: str = "rubric",
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
        fallback = _handle_judge_failure(
            exc,
            judge=judge,
            strict=strict,
            context=context,
        )
        if fallback is not None:
            return fallback
        raise

    logger.info(
        "Judge rubric scored (%s, model=%s): score=%.3f",
        context,
        judge.qualified,
        normalized,
    )
    passed = 1 if normalized >= 1.0 else 0
    return ScoreOutcome(
        score=normalized,
        scorer="judge_rubric",
        passed=passed,
        total=1,
        rationale=parsed.rationale,
    )


_LISTWISE_MAX = 10.0


def parse_listwise_response(text: str, count: int) -> list[ListwiseItem]:
    """Parse a listwise judge response into ``count`` items aligned by 1-based id."""
    payload = extract_json_object(text)
    raw_scores = payload.get("scores")
    if not isinstance(raw_scores, list):
        raise JudgeParseError("listwise response missing 'scores' array")

    items: list[ListwiseItem | None] = [None] * count
    for entry in raw_scores:
        if not isinstance(entry, dict):
            continue
        try:
            idx = int(entry["id"]) - 1
        except (KeyError, TypeError, ValueError):
            continue
        if not 0 <= idx < count:
            continue
        score = entry.get("score")
        if score is None:
            continue
        normalized = max(0.0, min(1.0, float(score) / _LISTWISE_MAX))
        rationale = entry.get("rationale")
        items[idx] = ListwiseItem(
            score=normalized,
            rationale=str(rationale).strip() if rationale is not None else None,
        )

    if all(item is None for item in items):
        raise JudgeParseError("listwise response scored no outputs")
    return [item or ListwiseItem(score=0.0) for item in items]


def judge_listwise(
    judge: JudgeContext,
    *,
    prompt: str,
    outputs: list[str],
    rubric: str,
    params: GenerationParams | None = None,
    strict: bool = False,
    context: str = "listwise",
) -> list[ListwiseItem]:
    """Score several outputs for one task *relative to each other* in a single call.

    Outputs are presented anonymized as ``Output 1..N``; the caller is responsible
    for shuffling order to mitigate position bias. Returns one item per input
    output, aligned to the given order.
    """
    blocks = "\n\n".join(
        f"--- Output {i} ---\n{text}" for i, text in enumerate(outputs, start=1)
    )
    user_content = (
        f"Compare and score the following {len(outputs)} model outputs for the "
        "SAME task, judging them relative to each other.\n\n"
        f"Task prompt:\n{prompt}\n\n"
        f"Rubric:\n{rubric}\n\n"
        f"Outputs:\n{blocks}\n\n"
        "Score each output on an integer scale from 1 to 10 using the FULL range. "
        "Spread the scores to reflect real quality gaps; give two outputs the same "
        "score only if they are genuinely indistinguishable. Respond with JSON "
        'only: {"scores": [{"id": <output number>, "score": <1-10>, '
        '"rationale": "<brief explanation>"}, ...]} with one entry per output.'
    )

    try:
        raw = _call_judge(judge, user_content, params=params)
        return parse_listwise_response(raw, len(outputs))
    except Exception as exc:
        if isinstance(exc, JudgeParseError):
            logger.warning(
                "Judge listwise parse failed (%s, model=%s): %s",
                context,
                judge.qualified,
                exc,
            )
            return [ListwiseItem(score=0.0) for _ in outputs]
        if not _is_provider_error(exc):
            raise
        message = (
            f"Judge listwise call failed ({context}, model={judge.qualified}): {exc}"
        )
        logger.error(message)
        if strict:
            raise JudgeProviderError(message) from exc
        return [ListwiseItem(score=0.0) for _ in outputs]


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
    strict: bool = False,
    context: str = "pairwise",
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
        if _is_provider_error(exc):
            message = (
                f"Judge pairwise call failed ({context}, model={judge.qualified}): "
                f"{exc}"
            )
            logger.error(message)
            if strict:
                raise JudgeProviderError(message) from exc
        else:
            logger.warning(
                "Judge pairwise comparison failed (%s, model=%s): %s",
                context,
                judge.qualified,
                exc,
            )
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
