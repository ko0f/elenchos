from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from elenchos.benchmarks.schema import JudgeRubricScorer
from elenchos.providers.base import Completion, GenerationParams, Message
from elenchos.scoring.deterministic import score_task_output
from elenchos.scoring.judge import (
    JudgeContext,
    JudgeParseError,
    extract_json_object,
    judge_rubric,
    normalize_rubric_score,
    pairwise_winner,
    parse_judge_response,
)


@dataclass
class MockJudgeProvider:
    name: str = "mock"
    responses: list[str] = field(default_factory=list)
    call_index: int = 0

    def list_models(self) -> list[str]:
        return ["judge-model"]

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
            else '{"winner": "tie", "rationale": "fallback"}'
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


@pytest.fixture
def judge_ctx() -> JudgeContext:
    provider = MockJudgeProvider()
    return JudgeContext(
        provider=provider,
        model="judge-model",
        qualified="mock/judge-model",
    )


def test_extract_json_object_raw():
    payload = extract_json_object('{"score": 4, "max": 5, "rationale": "good"}')
    assert payload["score"] == 4


def test_extract_json_object_fenced():
    text = 'Here is the result:\n```json\n{"winner": "A"}\n```'
    payload = extract_json_object(text)
    assert payload["winner"] == "A"


def test_extract_json_object_malformed_raises():
    with pytest.raises(JudgeParseError):
        extract_json_object("not json at all")


def test_parse_judge_response_rubric():
    parsed = parse_judge_response('{"score": 3, "max": 5, "rationale": "ok"}')
    assert parsed.score == 3.0
    assert parsed.max_score == 5.0
    assert normalize_rubric_score(parsed) == pytest.approx(0.6)


def test_normalize_rubric_score_defaults_max_to_five():
    parsed = parse_judge_response('{"score": 4}')
    assert normalize_rubric_score(parsed) == pytest.approx(0.8)


def test_judge_rubric_uses_provider(judge_ctx: JudgeContext):
    judge_ctx.provider.responses = [
        '{"score": 5, "max": 5, "rationale": "perfect"}',
    ]
    outcome = judge_rubric(
        judge_ctx,
        prompt="Say hi",
        output="Hello",
        rubric="5 = friendly greeting",
    )
    assert outcome.score == 1.0
    assert outcome.scorer == "judge_rubric"


def test_judge_rubric_malformed_returns_zero(judge_ctx: JudgeContext):
    judge_ctx.provider.responses = ["Sorry, I cannot score that."]
    outcome = judge_rubric(
        judge_ctx,
        prompt="Say hi",
        output="Hello",
        rubric="5 = friendly",
    )
    assert outcome.score == 0.0


def test_pairwise_both_orders_average_to_a(judge_ctx: JudgeContext):
    judge_ctx.provider.responses = [
        '{"winner": "A", "rationale": "first"}',
        '{"winner": "B", "rationale": "second"}',
    ]
    winner, _ = pairwise_winner(
        judge_ctx,
        prompt="task",
        output_a="answer a",
        output_b="answer b",
    )
    assert winner == "A"


def test_pairwise_conflicting_votes_is_tie(judge_ctx: JudgeContext):
    judge_ctx.provider.responses = [
        '{"winner": "A", "rationale": "first"}',
        '{"winner": "A", "rationale": "second"}',
    ]
    winner, _ = pairwise_winner(
        judge_ctx,
        prompt="task",
        output_a="answer a",
        output_b="answer b",
    )
    assert winner == "tie"


def test_score_task_output_judge_rubric(judge_ctx: JudgeContext):
    judge_ctx.provider.responses = [
        '{"score": 4, "max": 5, "rationale": "good"}',
    ]
    outcome = score_task_output(
        "Paris is nice",
        [
            JudgeRubricScorer(
                type="judge_rubric",
                rubric="5 = mentions Paris",
            )
        ],
        prompt="Capital of France?",
        judge=judge_ctx,
    )
    assert outcome.score == pytest.approx(0.8)
    assert outcome.scorer == "judge_rubric"
