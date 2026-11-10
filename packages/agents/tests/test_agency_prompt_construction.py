"""Agency rule prompt construction for Narrator and GMAgent (Phase 4 Task 2).

Task 2 says: test on prompt construction — the rule must travel with the cast
input and in the output field, exactly like the G-4 hallucination guard.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from monitor_agents.cast import AGENCY_RULE, build_cast
from monitor_agents.gm_agent import _GMReActSignature
from monitor_agents.narrator.agent import Narrator
from monitor_agents.narrator.narrator import NarratorSignature


class TestSignatureSurfaces:
    def test_narrator_cast_input_carries_the_rule(self):
        field = NarratorSignature.input_fields["cast_context"]
        assert "[PLAYER-CONTROLLED]" in field.json_schema_extra["desc"]
        assert "NEVER" in field.json_schema_extra["desc"]

    def test_narrator_output_field_carries_the_rule(self):
        desc = NarratorSignature.output_fields["narrative_text"].json_schema_extra["desc"]
        assert "[PLAYER-CONTROLLED]" in desc
        assert "Never contradict a stated NPC intent" in desc

    def test_narrator_docstring_states_the_rule(self):
        doc = NarratorSignature.__doc__ or ""
        assert "NEVER decide actions, speech, thoughts, or feelings" in doc

    def test_gm_signature_cast_input_carries_the_rule(self):
        field = _GMReActSignature.input_fields["cast_context"]
        assert "[PLAYER-CONTROLLED]" in field.json_schema_extra["desc"]

    def test_gm_narrative_draft_output_carries_the_rule(self):
        desc = _GMReActSignature.output_fields["narrative_draft"].json_schema_extra["desc"]
        assert "[PLAYER-CONTROLLED]" in desc

    def test_agency_rule_names_both_controllers(self):
        assert "PLAYER-CONTROLLED" in AGENCY_RULE
        assert "GM-CONTROLLED" in AGENCY_RULE


class TestNarratorPromptConstruction:
    @pytest.mark.asyncio
    async def test_generate_once_injects_cast_block_and_npc_state(self):
        narrator = Narrator()
        captured: dict[str, Any] = {}

        def _record_module(**kwargs: Any) -> Any:
            captured.update(kwargs)
            return SimpleNamespace(
                narrative_text="prose",
                proposed_changes="[]",
                narrative_time_elapsed="5",
                suggested_actions="[]",
                npc_emotional_states="{}",
            )

        cast = build_cast(
            controlled_ids=["pc1", "pc2"],
            speaker_id="pc1",
            actor_context={"id": "pc1", "name": "Ana"},
            entity_context=[{"id": "n1", "name": "Vex", "entity_type": "character"}],
            scene_id=str(uuid4()),
        )
        context = {
            "entities": [],
            "memories": [],
            "turns": [],
            "source_profile": {},
            "actor": {"id": "pc1", "name": "Ana"},
            "cast": cast.model_dump(mode="json"),
            "npc_profiles": {"n1": {"name": "Vex"}},
            "npc_memories": {"n1": {"name": "Vex", "memories": ["saw the ledger vanish"]}},
            "npc_facts": {"n1": {"name": "Vex", "facts": ["the ledger is gone"]}},
            "npc_intents": [{"entity_id": "n1", "name": "Vex", "intent": "hide the theft"}],
        }

        with (
            patch.object(narrator, "_resolve_tone_context", AsyncMock(return_value="tone")),
            patch.object(narrator, "_narrator_module", _record_module),
        ):
            await narrator._generate_once(
                user_input="I ask about the ledger",
                resolution=None,
                context=context,
                game_context=None,
            )

        # The dedicated cast input carries the roster + the rule.
        assert "[PLAYER-CONTROLLED] Ana" in captured["cast_context"]
        assert "(SPEAKING NOW)" in captured["cast_context"]
        assert AGENCY_RULE in captured["cast_context"]

        # The block also lands next to the actor block (G-4 guard pattern).
        assert "CAST (who is who" in captured["profile_context"]

        # Task 9: intents are in the NPC STATE block and marked un-contradictable.
        assert "intent: hide the theft" in captured["profile_context"]
        assert "do not contradict" in captured["profile_context"]
        # Task 7: per-NPC recall.
        assert "recalls: saw the ledger vanish" in captured["profile_context"]
        # Task 8: only the NPC's known facts.
        assert "knows: the ledger is gone" in captured["profile_context"]

    @pytest.mark.asyncio
    async def test_generate_once_tolerates_absent_cast(self):
        narrator = Narrator()
        captured: dict[str, Any] = {}

        def _record_module(**kwargs: Any) -> Any:
            captured.update(kwargs)
            return SimpleNamespace(
                narrative_text="prose",
                proposed_changes="[]",
                narrative_time_elapsed="5",
                suggested_actions="[]",
                npc_emotional_states="{}",
            )

        with (
            patch.object(narrator, "_resolve_tone_context", AsyncMock(return_value="tone")),
            patch.object(narrator, "_narrator_module", _record_module),
        ):
            await narrator._generate_once(
                user_input="hello",
                resolution=None,
                context={"entities": [], "memories": [], "turns": [], "source_profile": {}},
                game_context=None,
            )

        assert captured["cast_context"] == ""
        assert "CAST (who is who" not in captured["profile_context"]
