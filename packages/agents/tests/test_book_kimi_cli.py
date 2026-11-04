"""Tests for the Kimi coverage model: tools stay off, and limits hold (prototype, I-17)."""

import json
from pathlib import Path

import pytest
from monitor_agents.book_decomposition.kimi_cli import (
    KimiAnswerError,
    KimiCoverageModel,
    parse_answer,
)
from monitor_agents.book_decomposition.pacing import RunGuard, RunStopped
from monitor_data.schemas.book_graph import AtomKind


def _stream(content: str) -> str:
    rows = [
        {"role": "meta", "type": "system.version", "version": "2"},
        {"role": "assistant", "content": content},
        {"role": "meta", "type": "session.resume_hint", "content": "resume"},
    ]
    return "\n".join(json.dumps(row) for row in rows)


GOOD = _stream(json.dumps({"gaps": [{"label": "P1", "kind": "fact", "missing": "M", "quote": "q"}]}))


def _fake(results):
    calls = []

    async def run(command: list[str], folder: Path):
        agent = Path(command[command.index("--agent-file") + 1])
        calls.append({"command": command, "folder": folder, "agent": agent.read_text(), "files": sorted(p.name for p in folder.iterdir())})
        result = results.pop(0) if isinstance(results, list) else results
        if isinstance(result, Exception):
            raise result
        return result

    return run, calls


def _model(results, **kwargs):
    run, calls = _fake(results)
    guard = RunGuard()
    return KimiCoverageModel("kimi-code/k3.1-pro", "Find gaps.", guard=guard, run_command=run, **kwargs), calls, guard


@pytest.mark.unit
async def test_every_call_has_tools_off_in_an_empty_folder():
    model, calls, _ = _model((0, GOOD, ""))
    answer = await model.find_gaps("[P1] PARAGRAPH: x")
    call = calls[0]
    assert "tools: []" in call["agent"]
    assert call["files"] == ["agent.md"]
    assert "--yolo" not in call["command"] and "--auto" not in call["command"]
    assert call["command"][call["command"].index("-m") + 1] == "kimi-code/k3.1-pro"
    assert answer.gaps[0].kind == AtomKind.FACT
    assert not Path(call["folder"]).exists()


@pytest.mark.unit
async def test_prompt_carries_the_instructions_and_the_paragraphs():
    model, calls, _ = _model((0, GOOD, ""))
    await model.find_gaps("[P1] PARAGRAPH: book text")
    text = calls[0]["command"][-1]
    assert "Find gaps." in text and "book text" in text


@pytest.mark.unit
def test_answer_wrapped_in_prose_is_still_read():
    assert parse_answer(_stream('Here: {"gaps": []} done')).gaps == []


@pytest.mark.unit
@pytest.mark.parametrize("content", ["no json here", '{"gaps": [{"label": "P1"}]}', '{"gaps": 3}'])
def test_answer_that_does_not_fit_raises(content):
    with pytest.raises(KimiAnswerError):
        parse_answer(_stream(content))


@pytest.mark.unit
async def test_call_limit_stops_the_run_before_calling_again():
    model, calls, guard = _model((0, GOOD, ""), max_calls=1)
    await model.find_gaps("a")
    with pytest.raises(RunStopped):
        await model.find_gaps("b")
    assert len(calls) == 1
    assert "call limit" in guard.stopped_reason


@pytest.mark.unit
async def test_three_failures_in_a_row_stop_the_run():
    model, calls, guard = _model((1, "", "boom"))
    for _ in range(2):
        with pytest.raises(RuntimeError):
            await model.find_gaps("a")
    with pytest.raises(RunStopped):
        await model.find_gaps("a")
    assert guard.stopped


@pytest.mark.unit
async def test_a_success_resets_the_failure_count():
    model, _, guard = _model([(1, "", "x"), (1, "", "x"), (0, GOOD, ""), (1, "", "x"), (1, "", "x")])
    for expected in (RuntimeError, RuntimeError, None, RuntimeError, RuntimeError):
        if expected:
            with pytest.raises(expected):
                await model.find_gaps("a")
        else:
            await model.find_gaps("a")
    assert not guard.stopped


@pytest.mark.unit
async def test_usage_limit_message_stops_the_run_at_once():
    model, calls, guard = _model((1, "", "Usage limit reached for this plan"))
    with pytest.raises(RunStopped):
        await model.find_gaps("a")
    assert guard.stopped and len(calls) == 1


@pytest.mark.unit
async def test_batch_too_large_for_one_argument_is_refused_before_calling():
    model, calls, _ = _model((0, GOOD, ""))
    with pytest.raises(ValueError, match="too large"):
        await model.find_gaps("x" * 130_000)
    assert calls == [] and model.calls == 0


@pytest.mark.unit
async def test_kimis_five_hour_limit_stops_the_run_at_once():
    message = "provider.api_error: 429 You've reached your 5-hour usage limit. Your quota will reset"
    model, calls, guard = _model((1, "", message))
    with pytest.raises(RunStopped):
        await model.find_gaps("a")
    assert guard.stopped and len(calls) == 1
