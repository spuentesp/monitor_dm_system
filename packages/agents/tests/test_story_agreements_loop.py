from __future__ import annotations

import pytest

from monitor_agents import story_agreements as sa
from monitor_agents.loops.story_agreements_loop import StoryAgreementsLoop


@pytest.fixture(autouse=True)
def _disable_dspy(monkeypatch):
    monkeypatch.setattr(sa, "_DSPY_AVAILABLE", False)


def _loop(**overrides):
    values = {
        "setting_intro": {
            "universe_name": "Tenebris",
            "intro_text": "This story takes place in **Tenebris**, around Dead Flag Station.",
        },
        "character_name": "Mara",
        "default_tone": "grim",
    }
    values.update(overrides)
    return StoryAgreementsLoop(**values)


@pytest.mark.asyncio
async def test_compact_interview_asks_three_categories_then_summarizes():
    loop = _loop()

    started = await loop.start()
    assert started["category"] == "premise"
    assert "Tenebris" in started["gm_message"]
    assert "Mara" in started["gm_message"]

    second = await loop.process_player_input(
        "A salvage mystery where Mara decides whether the station should survive."
    )
    assert second["category"] == "themes"
    assert second["question_number"] == 2

    third = await loop.process_player_input(
        "Isolation and found family, with slow and oppressive pacing."
    )
    assert third["category"] == "boundaries"
    assert third["question_number"] == 3

    completed = await loop.process_player_input(
        "No harm to children. Veil explicit sexual content."
    )
    assert completed["complete"] is True
    assert completed["awaiting_confirmation"] is True
    agreements = completed["agreements"]
    assert agreements.story_premise.startswith("A salvage mystery")
    assert agreements.themes == [
        "Isolation and found family, with slow and oppressive pacing."
    ]
    assert agreements.boundary_notes == [
        "No harm to children. Veil explicit sexual content."
    ]
    assert agreements.needs_review is True
    assert agreements.confirmed is False
    assert "Begin Story" in completed["gm_message"]


@pytest.mark.asyncio
async def test_authored_questions_override_default_wording():
    authored = [
        {"question_text": "What mission brings this crew together?"},
        {"question_text": "Which themes should dominate?"},
        {"question_text": "Name lines and veils."},
    ]
    loop = _loop(authored_questions=authored)

    first = await loop.start()
    assert first["gm_message"].endswith(authored[0]["question_text"])
    second = await loop.process_player_input("Recover the black box.")
    assert second["gm_message"] == authored[1]["question_text"]
    third = await loop.process_player_input("Trust and scarcity.")
    assert third["gm_message"] == authored[2]["question_text"]


@pytest.mark.asyncio
async def test_text_after_summary_creates_revision_without_confirming():
    loop = _loop()
    await loop.start()
    await loop.process_player_input("A haunted salvage story.")
    await loop.process_player_input("Dread and loyalty.")
    completed = await loop.process_player_input("No lines or veils.")
    assert completed["agreements"].revision == 0

    revised = await loop.process_player_input("Make the pacing more deliberate.")

    assert revised["complete"] is True
    assert revised["agreements"].revision == 1
    assert revised["agreements"].confirmed is False
    assert loop.state.answers[-1].category.value == "revision"


def test_checkpoint_rehydrates_question_progress():
    original = _loop()
    original._state = original.state.model_copy(update={"question_index": 1})

    restored = _loop(checkpoint=original.checkpoint())

    assert restored.state.question_index == 1
    assert restored.state.setting_intro["universe_name"] == "Tenebris"
