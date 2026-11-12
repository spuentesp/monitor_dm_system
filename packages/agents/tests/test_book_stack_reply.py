"""Stacking answers the model gives for "nothing to merge" are accepted, not counted as failures (I-17)."""

from __future__ import annotations

import pytest

from monitor_agents.book_decomposition.review import (
    stack_decision_from_reply,
    stack_decision_from_value,
)


@pytest.mark.unit
@pytest.mark.parametrize("raw", [[], {"stacks": []}, {}])
def test_empty_answers_mean_no_stacks(raw):
    assert stack_decision_from_value(raw).stacks == []


@pytest.mark.unit
@pytest.mark.parametrize("reply", ['{"stacks": []}', '```json\n{"stacks": []}\n```', "[]"])
def test_a_rejected_reply_that_is_an_empty_stack_list_is_recovered(reply):
    decision = stack_decision_from_reply(reply)
    assert decision is not None
    assert decision.stacks == []


@pytest.mark.unit
@pytest.mark.parametrize("reply", [None, "", "not json", '{"something": 1}', "The request was rejected"])
def test_other_replies_are_not_recovered(reply):
    assert stack_decision_from_reply(reply) is None


class _Prediction:
    def __init__(self, result):
        self.result = result


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stack_recovers_when_dspy_rejects_a_bare_list_and_caps_the_output(monkeypatch):
    from pydantic import ValidationError

    from monitor_agents.book_decomposition import review

    seen: dict = {}

    def module(**kwargs):
        seen.update(kwargs)
        review.StackDecision.model_validate([])  # raises the same ValidationError DSPy surfaced
        return _Prediction(None)

    monkeypatch.setenv("MONITOR_BOOK_STACK_MAX_TOKENS", "4096")
    monkeypatch.setattr(review, "run_metered", lambda lm, fn: (fn(), 0, 0))
    model = review.DspyReviewModel(lm=object())
    monkeypatch.setattr(model, "_stack", module)

    with pytest.raises(ValidationError):
        review.StackDecision.model_validate([])
    decision = await model.stack("prompt")

    assert decision.stacks == []
    assert seen["config"] == {"max_tokens": 4096}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stack_leaves_the_output_uncapped_by_default(monkeypatch):
    from monitor_agents.book_decomposition import review

    seen: dict = {}

    def module(**kwargs):
        seen.update(kwargs)
        return _Prediction({"stacks": []})

    monkeypatch.delenv("MONITOR_BOOK_STACK_MAX_TOKENS", raising=False)
    monkeypatch.setattr(review, "run_metered", lambda lm, fn: (fn(), 0, 0))
    model = review.DspyReviewModel(lm=object())
    monkeypatch.setattr(model, "_stack", module)

    decision = await model.stack("prompt")

    assert decision.stacks == []
    assert seen["config"] == {}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stack_reraises_the_original_error_when_the_rejected_list_is_not_a_valid_answer(monkeypatch):
    from pydantic import ValidationError

    from monitor_agents.book_decomposition import review

    raised: list[ValidationError] = []

    def module(**kwargs):
        try:
            review.StackDecision.model_validate([1, 2])  # a bare list of non-stacks is not recoverable
        except ValidationError as exc:
            raised.append(exc)
            raise
        return _Prediction(None)

    monkeypatch.setattr(review, "run_metered", lambda lm, fn: (fn(), 0, 0))
    model = review.DspyReviewModel(lm=object())
    monkeypatch.setattr(model, "_stack", module)

    with pytest.raises(ValidationError) as excinfo:
        await model.stack("prompt")

    assert excinfo.value is raised[0]


@pytest.mark.unit
def test_extra_body_comes_from_the_environment(monkeypatch):
    from monitor_agents.book_decomposition.extractor import extra_body_from_env

    monkeypatch.delenv("MONITOR_BOOK_LLM_EXTRA_BODY", raising=False)
    assert extra_body_from_env() == {}
    monkeypatch.setenv("MONITOR_BOOK_LLM_EXTRA_BODY", '{"thinking": {"type": "disabled"}}')
    assert extra_body_from_env() == {"thinking": {"type": "disabled"}}
    for bad in ("not json", "[1]", '"x"'):
        monkeypatch.setenv("MONITOR_BOOK_LLM_EXTRA_BODY", bad)
        assert extra_body_from_env() == {}
