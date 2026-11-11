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
