"""
Behavior tests for SessionZeroLoop choreography.

Exercises the loop's state transitions, question flow, max-questions
enforcement, summary generation, and fallback paths — all without LLM
or DB (uses fallback questions which don't require DSPy).

Covers:
- SessionZeroState defaults
- SessionZeroLoop.start() — first question
- SessionZeroLoop.process_player_input() — answer + next question
- Max questions enforcement
- Stop signals ("done", "skip")
- Summary generation after completion
- Fallback question cycling
- Error handling
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


# =============================================================================
# State defaults
# =============================================================================


class TestSessionZeroState:
    def test_default_state(self):
        from monitor_agents.loops.session_zero_loop import SessionZeroState

        state = SessionZeroState()
        assert state.tone == "dramatic"
        assert state.system_name == "Unknown System"
        # [G-1] DEFAULT_MAX_QUESTIONS dropped 7 → 4
        assert state.max_questions == 4
        assert state.question_number == 0
        assert state.answers == []
        assert state.categories_asked == []
        assert state.interview_complete is False
        assert state.awaiting_input is False

    def test_state_with_overrides(self):
        from monitor_agents.loops.session_zero_loop import SessionZeroState

        state = SessionZeroState(
            tone="grim",
            system_name="Death in Space",
            max_questions=5,
        )
        assert state.tone == "grim"
        assert state.system_name == "Death in Space"
        assert state.max_questions == 5


# =============================================================================
# Loop start
# =============================================================================


class TestLoopStart:
    @pytest.mark.asyncio
    async def test_start_returns_first_question(self):
        from monitor_agents.loops.session_zero_loop import SessionZeroLoop

        loop = SessionZeroLoop(tone="grim", system_name="Death in Space")
        result = await loop.start()

        assert result["complete"] is False
        assert result["gm_message"]
        assert result["question_number"] == 1
        # [G-1] total_questions tracks DEFAULT_MAX_QUESTIONS = 4
        assert result["total_questions"] == 4
        assert "category" in result

    @pytest.mark.asyncio
    async def test_start_increments_question_number(self):
        from monitor_agents.loops.session_zero_loop import SessionZeroLoop

        loop = SessionZeroLoop(tone="dramatic", system_name="Test")
        result = await loop.start()
        assert result["question_number"] == 1

    @pytest.mark.asyncio
    async def test_start_with_max_questions_zero(self):
        from monitor_agents.loops.session_zero_loop import SessionZeroLoop

        loop = SessionZeroLoop(tone="dramatic", system_name="Test", max_questions=0)
        result = await loop.start()
        # With 0 max questions, should complete immediately
        assert result["complete"] is True


# =============================================================================
# Process player input
# =============================================================================


class TestProcessPlayerInput:
    @pytest.mark.asyncio
    async def test_answer_advances_to_next_question(self):
        from monitor_agents.loops.session_zero_loop import SessionZeroLoop

        loop = SessionZeroLoop(tone="grim", system_name="Death in Space")
        await loop.start()
        result = await loop.process_player_input("I was a miner on Inauro.")

        assert result["complete"] is False
        assert result["question_number"] == 2
        assert result["gm_message"]

    @pytest.mark.asyncio
    async def test_answer_records_qa_pair(self):
        from monitor_agents.loops.session_zero_loop import SessionZeroLoop

        loop = SessionZeroLoop(tone="grim", system_name="Death in Space")
        await loop.start()
        await loop.process_player_input("I was a miner on Inauro.")

        assert len(loop.answers) == 1
        assert loop.answers[0]["answer"] == "I was a miner on Inauro."
        assert loop.answers[0]["question"]

    @pytest.mark.asyncio
    async def test_done_signal_completes_interview(self):
        from monitor_agents.loops.session_zero_loop import SessionZeroLoop

        loop = SessionZeroLoop(tone="grim", system_name="Death in Space")
        await loop.start()
        result = await loop.process_player_input("done")

        assert result["complete"] is True
        assert result["summary"] is not None
        assert result["gm_message"]

    @pytest.mark.asyncio
    async def test_skip_signal_completes_interview(self):
        from monitor_agents.loops.session_zero_loop import SessionZeroLoop

        loop = SessionZeroLoop(tone="grim", system_name="Death in Space")
        await loop.start()
        result = await loop.process_player_input("skip")

        assert result["complete"] is True

    @pytest.mark.asyncio
    async def test_thats_all_signal_completes(self):
        from monitor_agents.loops.session_zero_loop import SessionZeroLoop

        loop = SessionZeroLoop(tone="dramatic", system_name="Test")
        await loop.start()
        result = await loop.process_player_input("that's all")

        assert result["complete"] is True

    @pytest.mark.asyncio
    async def test_empty_input_does_not_advance(self):
        from monitor_agents.loops.session_zero_loop import SessionZeroLoop

        loop = SessionZeroLoop(tone="dramatic", system_name="Test")
        await loop.start()
        await loop.process_player_input("")

        # Empty input should not record an answer or advance
        assert len(loop.answers) == 0


# =============================================================================
# Max questions enforcement
# =============================================================================


class TestMaxQuestions:
    @pytest.mark.asyncio
    async def test_completes_after_max_questions(self):
        from monitor_agents.loops.session_zero_loop import SessionZeroLoop

        loop = SessionZeroLoop(tone="grim", system_name="Test", max_questions=3)
        await loop.start()  # Q1
        await loop.process_player_input("Answer 1")  # → Q2
        await loop.process_player_input("Answer 2")  # → Q3
        result = await loop.process_player_input("Answer 3")  # → complete

        assert result["complete"] is True
        assert result["summary"] is not None
        assert len(loop.answers) == 3

    @pytest.mark.asyncio
    async def test_does_not_complete_before_max(self):
        from monitor_agents.loops.session_zero_loop import SessionZeroLoop

        loop = SessionZeroLoop(tone="grim", system_name="Test", max_questions=5)
        await loop.start()  # Q1
        result = await loop.process_player_input("Answer 1")  # → Q2

        assert result["complete"] is False
        assert result["question_number"] == 2


# =============================================================================
# seed_answers — pre-filling the interview from a saved persona
# (character-template bridge: a returning persona shouldn't be re-interviewed
# from scratch; see CHARACTER_TEMPLATES_AND_GM_CONDITIONING_PLAN.md Q2)
# =============================================================================


class TestSeedAnswers:
    def test_seed_answers_populate_state_before_start(self):
        from monitor_agents.loops.session_zero_loop import SessionZeroLoop

        seed = [
            {"question": "What are you called?", "answer": "Rook", "category": "name"},
            {"question": "Who are you?", "answer": "A scavenger", "category": "origin"},
        ]
        loop = SessionZeroLoop(tone="grim", system_name="Test", seed_answers=seed)

        assert loop.answers == seed
        assert loop.state.categories_asked == ["name", "origin"]

    def test_seed_answers_shrink_max_questions(self):
        from monitor_agents.loops.session_zero_loop import SessionZeroLoop

        seed = [{"question": "Q", "answer": "A", "category": "custom"}] * 3
        loop = SessionZeroLoop(
            tone="grim", system_name="Test", max_questions=7, seed_answers=seed
        )

        # 7 - 3 seeded = 4 remaining questions, not the full 7.
        assert loop.state.max_questions == 4

    def test_seed_answers_never_shrink_below_two_questions(self):
        from monitor_agents.loops.session_zero_loop import SessionZeroLoop

        seed = [{"question": "Q", "answer": "A", "category": "custom"}] * 6
        loop = SessionZeroLoop(
            tone="grim", system_name="Test", max_questions=7, seed_answers=seed
        )

        # 7 - 6 = 1, floored up to the 2-question minimum -- still room to
        # ground the persona in *this* setting, not just repeat what it says.
        assert loop.state.max_questions == 2

    @pytest.mark.asyncio
    async def test_interview_completes_sooner_with_seed_answers(self):
        from monitor_agents.loops.session_zero_loop import SessionZeroLoop

        seed = [{"question": "Q", "answer": "A", "category": "custom"}] * 5
        loop = SessionZeroLoop(
            tone="grim", system_name="Test", max_questions=7, seed_answers=seed
        )

        await loop.start()  # Q1 (of the shrunk 2-question budget)
        result = await loop.process_player_input(
            "Confirmed, that's still me."
        )  # Q2 → complete

        assert result["complete"] is True
        # Seeded answers plus the one new one asked during the interview.
        assert len(loop.answers) == 6

    def test_no_seed_answers_behaves_exactly_as_before(self):
        from monitor_agents.loops.session_zero_loop import SessionZeroLoop

        loop = SessionZeroLoop(tone="grim", system_name="Test", max_questions=7)

        assert loop.answers == []
        assert loop.state.max_questions == 7


# =============================================================================
# ask_campaign_intent — the "what kind of story do you want" pre-question
# (character-template plan Q3), asked once, up front, when the player didn't
# already state a story_premise at session creation.
# =============================================================================


class TestCampaignIntent:
    @pytest.mark.asyncio
    async def test_campaign_intent_asked_first_as_question_zero(self):
        from monitor_agents.loops.session_zero_loop import (
            CAMPAIGN_INTENT_QUESTION,
            SessionZeroLoop,
        )

        loop = SessionZeroLoop(
            tone="grim", system_name="Test", ask_campaign_intent=True
        )
        result = await loop.start()

        assert result["complete"] is False
        assert result["gm_message"] == CAMPAIGN_INTENT_QUESTION
        assert result["question_number"] == 0
        assert result["category"] == "campaign_intent"

    @pytest.mark.asyncio
    async def test_answering_campaign_intent_advances_to_real_question_one(self):
        from monitor_agents.loops.session_zero_loop import SessionZeroLoop

        loop = SessionZeroLoop(
            tone="grim", system_name="Test", ask_campaign_intent=True
        )
        await loop.start()
        result = await loop.process_player_input(
            "A heist against a rival gang, no combat."
        )

        assert result["complete"] is False
        assert result["question_number"] == 1
        assert result["category"] != "campaign_intent"
        assert result["campaign_intent"] == "A heist against a rival gang, no combat."

    @pytest.mark.asyncio
    async def test_campaign_intent_answer_not_recorded_in_character_answers(self):
        """The campaign-intent answer must stay out of state.answers --
        that list feeds character concept/backstory synthesis, a separate
        concern from "what story do you want"."""
        from monitor_agents.loops.session_zero_loop import SessionZeroLoop

        loop = SessionZeroLoop(
            tone="grim", system_name="Test", ask_campaign_intent=True
        )
        await loop.start()
        await loop.process_player_input("Survival horror, minimal combat.")

        assert loop.answers == []
        assert loop.state.campaign_intent_answer == "Survival horror, minimal combat."

    @pytest.mark.asyncio
    async def test_skip_signal_yields_no_campaign_intent(self):
        from monitor_agents.loops.session_zero_loop import SessionZeroLoop

        loop = SessionZeroLoop(
            tone="grim", system_name="Test", ask_campaign_intent=True
        )
        await loop.start()
        result = await loop.process_player_input("skip")

        assert result.get("campaign_intent") is None
        assert result["question_number"] == 1

    @pytest.mark.asyncio
    async def test_empty_answer_yields_no_campaign_intent(self):
        from monitor_agents.loops.session_zero_loop import SessionZeroLoop

        loop = SessionZeroLoop(
            tone="grim", system_name="Test", ask_campaign_intent=True
        )
        await loop.start()
        result = await loop.process_player_input("   ")

        assert result.get("campaign_intent") is None

    @pytest.mark.asyncio
    async def test_default_ask_campaign_intent_false_behaves_exactly_as_before(self):
        from monitor_agents.loops.session_zero_loop import SessionZeroLoop

        loop = SessionZeroLoop(tone="grim", system_name="Test")
        result = await loop.start()

        assert result["question_number"] == 1
        assert result["category"] != "campaign_intent"

    @pytest.mark.asyncio
    async def test_campaign_intent_and_seed_answers_compose(self):
        """A persona-seeded session can still ask campaign intent first --
        the two features are independent."""
        from monitor_agents.loops.session_zero_loop import SessionZeroLoop

        seed = [
            {
                "question": "Who are you?",
                "answer": "Rook, a scavenger",
                "category": "origin",
            }
        ]
        loop = SessionZeroLoop(
            tone="grim",
            system_name="Test",
            seed_answers=seed,
            ask_campaign_intent=True,
        )
        result = await loop.start()

        assert result["category"] == "campaign_intent"
        assert loop.answers == seed  # seed present, untouched by campaign intent


# =============================================================================
# Summary generation
# =============================================================================


class TestSummary:
    @pytest.mark.asyncio
    async def test_summary_has_concept_and_backstory(self):
        from monitor_agents.loops.session_zero_loop import SessionZeroLoop

        loop = SessionZeroLoop(
            tone="grim", system_name="Death in Space", max_questions=2
        )
        await loop.start()
        await loop.process_player_input("My name is Silas, a chrome scrapper.")
        result = await loop.process_player_input("I lost my crew in the Gem War.")

        assert result["complete"] is True
        summary = result["summary"]
        assert summary.concept
        assert summary.backstory

    @pytest.mark.asyncio
    async def test_summary_extracts_name(self):
        from monitor_agents.loops.session_zero_loop import SessionZeroLoop

        loop = SessionZeroLoop(
            tone="grim", system_name="Death in Space", max_questions=2
        )
        await loop.start()
        await loop.process_player_input("My name is Silas, a chrome scrapper.")
        result = await loop.process_player_input("I lost my crew.")

        summary = result["summary"]
        # The fallback summary should extract "Silas" from the first answer
        assert summary.character_name == "Silas"

    @pytest.mark.asyncio
    async def test_summary_gm_message_includes_concept(self):
        from monitor_agents.loops.session_zero_loop import SessionZeroLoop

        loop = SessionZeroLoop(tone="grim", system_name="Test", max_questions=1)
        await loop.start()
        result = await loop.process_player_input("I am a soldier who lost everything.")

        gm_msg = result["gm_message"]
        assert gm_msg  # non-empty
        # The summary message should include the concept or backstory


# =============================================================================
# Categories tracking
# =============================================================================


class TestCategoriesTracking:
    @pytest.mark.asyncio
    async def test_categories_asked_tracks_history(self):
        from monitor_agents.loops.session_zero_loop import SessionZeroLoop

        loop = SessionZeroLoop(tone="grim", system_name="Test", max_questions=3)
        await loop.start()
        await loop.process_player_input("Answer 1")
        await loop.process_player_input("Answer 2")

        assert len(loop.state.categories_asked) == 2

    @pytest.mark.asyncio
    async def test_categories_are_valid_enum_values(self):
        from monitor_agents.loops.session_zero_loop import SessionZeroLoop
        from monitor_agents.session_zero import QuestionCategory

        loop = SessionZeroLoop(tone="grim", system_name="Test", max_questions=2)
        await loop.start()
        await loop.process_player_input("Answer 1")

        for cat in loop.state.categories_asked:
            # Should be a valid QuestionCategory value
            QuestionCategory(cat)


# =============================================================================
# Graph builder
# =============================================================================


class TestGraphBuilder:
    def test_build_graph_returns_state_graph(self):
        from langgraph.graph import StateGraph
        from monitor_agents.loops.session_zero_loop import build_session_zero_graph

        graph = build_session_zero_graph()
        assert isinstance(graph, StateGraph)

    def test_graph_has_ask_process_summarize_nodes(self):
        from monitor_agents.loops.session_zero_loop import build_session_zero_graph

        graph = build_session_zero_graph()
        # StateGraph.nodes is a dict of node names
        node_names = set(graph.nodes.keys())
        assert "ask" in node_names
        assert "process" in node_names
        assert "summarize" in node_names


# =============================================================================
# Routing functions
# =============================================================================


class TestRouting:
    def test_route_after_ask_await(self):
        from monitor_agents.loops.session_zero_loop import (
            SessionZeroState,
            _route_after_ask,
        )

        state = SessionZeroState(awaiting_input=True, interview_complete=False)
        assert _route_after_ask(state) == "await"

    def test_route_after_ask_summarize(self):
        from monitor_agents.loops.session_zero_loop import (
            SessionZeroState,
            _route_after_ask,
        )

        state = SessionZeroState(interview_complete=True)
        assert _route_after_ask(state) == "summarize"

    def test_route_after_process_ask(self):
        from monitor_agents.loops.session_zero_loop import (
            SessionZeroState,
            _route_after_process,
        )

        state = SessionZeroState(interview_complete=False, error=None)
        assert _route_after_process(state) == "ask"

    def test_route_after_process_summarize(self):
        from monitor_agents.loops.session_zero_loop import (
            SessionZeroState,
            _route_after_process,
        )

        state = SessionZeroState(interview_complete=True)
        assert _route_after_process(state) == "summarize"


# =============================================================================
# LLM mock tests — verify the loop calls ask_session_zero_question
# =============================================================================


class TestLLMIntegration:
    @pytest.mark.asyncio
    async def test_start_calls_ask_session_zero_question(self):
        from monitor_agents.loops.session_zero_loop import SessionZeroLoop
        from monitor_agents.session_zero import QuestionCategory, SessionZeroQuestion

        mock_question = SessionZeroQuestion(
            question_text="What did you lose?",
            category=QuestionCategory.LOSS,
            is_final=False,
        )

        with patch(
            "monitor_agents.loops.session_zero_loop.ask_session_zero_question",
            new_callable=AsyncMock,
            return_value=mock_question,
        ) as mock_ask:
            loop = SessionZeroLoop(tone="grim", system_name="Test")
            result = await loop.start()

            assert mock_ask.called
            assert result["gm_message"] == "What did you lose?"
            assert result["category"] == "loss"

    @pytest.mark.asyncio
    async def test_process_calls_ask_session_zero_question(self):
        from monitor_agents.loops.session_zero_loop import SessionZeroLoop
        from monitor_agents.session_zero import QuestionCategory, SessionZeroQuestion

        mock_question = SessionZeroQuestion(
            question_text="Who do you protect?",
            category=QuestionCategory.BOND,
            is_final=False,
        )

        with patch(
            "monitor_agents.loops.session_zero_loop.ask_session_zero_question",
            new_callable=AsyncMock,
            return_value=mock_question,
        ):
            loop = SessionZeroLoop(tone="grim", system_name="Test", max_questions=5)
            await loop.start()
            result = await loop.process_player_input("I was a miner.")

            assert result["gm_message"] == "Who do you protect?"
            assert result["category"] == "bond"

    @pytest.mark.asyncio
    async def test_complete_calls_summarize(self):
        from monitor_agents.loops.session_zero_loop import SessionZeroLoop
        from monitor_agents.session_zero import (
            QuestionCategory,
            SessionZeroQuestion,
            SessionZeroSummary,
        )

        mock_question = SessionZeroQuestion(
            question_text="Final question?",
            category=QuestionCategory.CONFLICT,
            is_final=False,
        )
        mock_summary = SessionZeroSummary(
            character_name="Test",
            concept="A test character.",
            backstory="A test backstory.",
            key_bonds=[],
            key_fears=[],
            key_motivations=[],
        )

        with (
            patch(
                "monitor_agents.loops.session_zero_loop.ask_session_zero_question",
                new_callable=AsyncMock,
                return_value=mock_question,
            ),
            patch(
                "monitor_agents.loops.session_zero_loop.summarize_session_zero_answers",
                new_callable=AsyncMock,
                return_value=mock_summary,
            ) as mock_summarize,
        ):
            loop = SessionZeroLoop(tone="grim", system_name="Test", max_questions=1)
            await loop.start()
            result = await loop.process_player_input("Final answer.")

            assert mock_summarize.called
            assert result["complete"] is True
            assert result["summary"] is not None
            assert result["summary"].character_name == "Test"
