import pytest
from monitor_agents.oracle import Oracle, Likelihood


def test_oracle_certainty():
    oracle = Oracle()

    # Certain should always be YES
    res_certain = oracle.resolve_question("Is water wet?", Likelihood.CERTAIN)
    assert res_certain["outcome"] == "yes"
    assert res_certain["is_yes"] is True

    # Impossible should always be NO
    res_impossible = oracle.resolve_question("Can pigs fly?", Likelihood.IMPOSSIBLE)
    assert res_impossible["outcome"] == "no"
    assert res_impossible["is_yes"] is False


def test_oracle_outcomes():
    oracle = Oracle()

    # Run many times to catch edge cases or just verify structure
    res = oracle.resolve_question("Is there a guard?", Likelihood.FIFTY_FIFTY)

    assert "question" in res
    assert "likelihood" in res
    assert "outcome" in res
    assert "roll" in res
    assert "dc" in res
    assert isinstance(res["is_yes"], bool)
    assert isinstance(res["is_exceptional"], bool)
    assert isinstance(res["has_complication"], bool)


def test_oracle_boundaries():
    oracle = Oracle()

    # Likelihood mapping check
    # Nearly Certain (DC 2)
    res = oracle.resolve_question("Test", Likelihood.NEARLY_CERTAIN)
    assert res["dc"] == 2

    # Nearly Impossible (DC 19)
    res = oracle.resolve_question("Test", Likelihood.NEARLY_IMPOSSIBLE)
    assert res["dc"] == 19


@pytest.mark.asyncio
async def test_oracle_run_method():
    """Oracle should have run method that can be called."""
    oracle = Oracle()

    # run() should not raise - just returns None or logs
    # It's an async method that can be awaited
    result = await oracle.run()
    assert result is None


def test_oracle_agent_id():
    """Oracle should have configurable agent_id."""
    oracle = Oracle(agent_id="test-oracle")
    assert oracle.agent_id == "test-oracle"


def test_oracle_default_agent_id():
    """Oracle should have default agent_id."""
    oracle = Oracle()
    assert oracle.agent_id == "oracle-1"


def test_oracle_has_run_method():
    """Oracle should have run method."""
    oracle = Oracle()
    assert hasattr(oracle, "run")


def test_oracle_resolve_question_returns_dict():
    """resolve_question should return a dict."""
    oracle = Oracle()
    res = oracle.resolve_question("Test question?")
    assert isinstance(res, dict)


def test_oracle_resolve_question_with_tension_score():
    """resolve_question should accept tension_score parameter."""
    oracle = Oracle()
    res = oracle.resolve_question("High tension question?", tension_score=0.9)
    assert res["question"] == "High tension question?"
    assert "outcome" in res


def test_oracle_resolve_question_with_custom_likelihood():
    """resolve_question should use passed likelihood."""
    oracle = Oracle()
    res = oracle.resolve_question("Custom likelihood?", Likelihood.UNLIKELY)
    assert (
        res["likelihood"].value == "unlikely"
        if hasattr(res["likelihood"], "value")
        else res["likelihood"] == "unlikely"
    )
