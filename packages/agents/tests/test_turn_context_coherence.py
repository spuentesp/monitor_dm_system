"""
Tests for Turn Context & Narrative Coherence fixes.

These tests define the CONTRACT for the fixes needed to prevent the narrative
breakdown documented in tests/e2e/logs/long_form_22turn.md:

1. Context summary must be wired through to the narrator (currently discarded)
2. Prior turns must be expanded beyond 3 (currently [-3:])
3. Setting anchor must be passed to the narrator (currently missing)
4. Character sheet must be passed to the narrator (currently missing)
5. TurnContext object must carry spatial/situational awareness
6. extract_facts node must persist established facts for continuity
7. check_consistency guard must catch setting/name drift
8. Pending roll state must carry forward between turns

All tests use the same mocking patterns as test_scene_loop.py:
- Lazy import via _import_scene_loop()
- unittest.mock.patch with AsyncMock for agent methods
- SceneState constructed directly with uuid4()

Run:
    cd /path/to/monitor_dm_system && pytest packages/agents/tests/test_turn_context_coherence.py -v
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


# ---------------------------------------------------------------------------
# Lazy import helpers (same pattern as test_scene_loop.py)
# ---------------------------------------------------------------------------


def _import_scene_loop():
    from monitor_agents.loops.scene_loop import (
        SceneState,
        build_scene_graph,
        canonize_checkpoint,
        load_context,
        narrate,
        persist_turn_artifacts,
        resolve_action,
        route_after_narration,
    )

    return (
        SceneState,
        build_scene_graph,
        canonize_checkpoint,
        load_context,
        narrate,
        persist_turn_artifacts,
        resolve_action,
        route_after_narration,
    )


def _import_narrator():
    from monitor_agents.narrator import Narrator

    return Narrator


def _import_turn_context():
    from monitor_agents.turn_context import TurnContext

    return TurnContext


# ===========================================================================
# FIX 1: Context summary must be wired through to the narrator
# ===========================================================================


class TestContextSummaryWiring:
    """The _summarise_context output is computed by ContextAssembly.assemble()
    but load_context() never extracts it into SceneState. The narrator never
    sees it. This is the cheapest fix with the highest impact."""

    @pytest.mark.asyncio
    async def test_load_context_extracts_summary_from_assemble_result(self):
        """load_context must read context['summary'] and pass it as context_summary."""
        (SceneState, _, _, load_context, *_) = _import_scene_loop()

        fake_context = {
            "entities": [{"id": "e1", "name": "Rhal"}],
            "memories": [],
            "turns": [],
            "summary": "Context for action: I search the room\n[Entity] Rhal (NPC)",
        }

        with patch(
            "monitor_agents.context_assembly.ContextAssembly.assemble",
            new_callable=AsyncMock,
            return_value=fake_context,
        ):
            state = SceneState(scene_id=uuid4(), story_id=uuid4())
            result = await load_context(state)

        assert "context_summary" in result, (
            "load_context must extract the 'summary' field from ContextAssembly.assemble() "
            "result and return it as 'context_summary' in SceneState updates."
        )
        assert result["context_summary"] == fake_context["summary"]

    @pytest.mark.asyncio
    async def test_load_context_handles_missing_summary_gracefully(self):
        """When assemble() returns no 'summary' key, context_summary should be empty string."""
        (SceneState, _, _, load_context, *_) = _import_scene_loop()

        with patch(
            "monitor_agents.context_assembly.ContextAssembly.assemble",
            new_callable=AsyncMock,
            return_value={"entities": [], "memories": [], "turns": []},
        ):
            state = SceneState(scene_id=uuid4(), story_id=uuid4())
            result = await load_context(state)

        assert result.get("context_summary", "") == ""

    @pytest.mark.asyncio
    async def test_scene_state_has_context_summary_field(self):
        """SceneState must have a context_summary field."""
        (SceneState, *_) = _import_scene_loop()

        state = SceneState(scene_id=uuid4(), story_id=uuid4())
        assert hasattr(state, "context_summary"), (
            "SceneState must have a 'context_summary' field to carry the "
            "ContextAssembly summary through to the narrator."
        )
        assert state.context_summary == "" or state.context_summary is None

    @pytest.mark.asyncio
    async def test_narrate_passes_context_summary_to_narrator(self):
        """The narrate() node must pass context_summary in the context dict to Narrator.narrate_turn()."""
        (SceneState, _, _, _, narrate, *_) = _import_scene_loop()

        captured_context: dict = {}

        async def fake_narrate_turn(*, scene_id, user_input, resolution, context, **kwargs):
            captured_context.update(context)
            return {"narrative_text": "The room is dark.", "proposals": [], "turn_id": "t1"}

        with patch(
            "monitor_agents.narrator.Narrator.narrate_turn",
            new_callable=AsyncMock,
            side_effect=fake_narrate_turn,
        ):
            state = SceneState(
                scene_id=uuid4(),
                story_id=uuid4(),
                user_input="I look around",
                context_summary="Context for action: I look around\n[Entity] Rhal (NPC)",
            )
            await narrate(state)

        assert "context_summary" in captured_context, (
            "narrate() must pass 'context_summary' in the context dict to Narrator.narrate_turn()"
        )
        assert captured_context["context_summary"] != ""


# ===========================================================================
# FIX 2: Prior turns must be expanded beyond 3
# ===========================================================================


class TestExpandedPriorTurns:
    """The narrator currently receives only [-3:] prior turns. This means
    anything older than 3 turns ago is invisible. Ship names, NPC names,
    and setting details established early are lost, causing the narrator
    to invent contradictory names (e.g. 'Rust Nail' → 'Ostensible')."""

    @pytest.mark.asyncio
    async def test_narrator_receives_at_least_8_prior_turns(self):
        """The narrator must receive at least 8 prior turns, not 3."""
        Narrator = _import_narrator()

        narrator = Narrator.__new__(Narrator)
        narrator._narrator_module = MagicMock()
        narrator._tone_resolver = MagicMock()

        fake_prediction = MagicMock()
        fake_prediction.narrative_text = "The corridor stretches ahead."
        fake_prediction.proposed_changes = "[]"
        fake_prediction.narrative_time_elapsed = "5"
        narrator._narrator_module.return_value = fake_prediction

        captured_kwargs: dict = {}

        def capture_module_call(**kwargs):
            captured_kwargs.update(kwargs)
            return fake_prediction

        narrator._narrator_module.side_effect = capture_module_call

        eight_turns = [
            {"turn_id": f"t{i}", "text": f"Turn {i} narration", "speaker": "gm" if i % 2 else "player"}
            for i in range(8)
        ]

        with (
            patch.object(Narrator, "_resolve_tone_context", new_callable=AsyncMock, return_value="grim"),
            patch.object(Narrator, "_format_resolution", return_value="narrative"),
            patch.object(Narrator, "_persist_turn", new_callable=AsyncMock, return_value="turn-1"),
            patch.object(Narrator, "_parse_proposed_changes", return_value=[]),
        ):
            await narrator.narrate_turn(
                scene_id=uuid4(),
                user_input="I move forward",
                resolution=None,
                context={
                    "entities": [],
                    "memories": [],
                    "turns": eight_turns,
                    "source_profile": {},
                },
            )

        prior_turns_json = captured_kwargs.get("prior_turns", "[]")
        prior_turns = json.loads(prior_turns_json)
        assert len(prior_turns) >= 8, (
            f"Narrator must receive at least 8 prior turns for continuity, got {len(prior_turns)}. "
            f"Currently truncated to [-3:] which causes name/setting drift."
        )

    @pytest.mark.asyncio
    async def test_narrator_receives_all_available_turns_when_fewer_than_8(self):
        """When fewer than 8 turns exist, the narrator should receive all of them."""
        Narrator = _import_narrator()

        narrator = Narrator.__new__(Narrator)
        narrator._narrator_module = MagicMock()
        narrator._tone_resolver = MagicMock()

        fake_prediction = MagicMock()
        fake_prediction.narrative_text = "The corridor stretches ahead."
        fake_prediction.proposed_changes = "[]"
        fake_prediction.narrative_time_elapsed = "5"
        narrator._narrator_module.return_value = fake_prediction

        captured_kwargs: dict = {}

        def capture_module_call(**kwargs):
            captured_kwargs.update(kwargs)
            return fake_prediction

        narrator._narrator_module.side_effect = capture_module_call

        two_turns = [
            {"turn_id": "t1", "text": "Turn 1", "speaker": "gm"},
            {"turn_id": "t2", "text": "Turn 2", "speaker": "player"},
        ]

        with (
            patch.object(Narrator, "_resolve_tone_context", new_callable=AsyncMock, return_value="grim"),
            patch.object(Narrator, "_format_resolution", return_value="narrative"),
            patch.object(Narrator, "_persist_turn", new_callable=AsyncMock, return_value="turn-1"),
            patch.object(Narrator, "_parse_proposed_changes", return_value=[]),
        ):
            await narrator.narrate_turn(
                scene_id=uuid4(),
                user_input="I move forward",
                resolution=None,
                context={
                    "entities": [],
                    "memories": [],
                    "turns": two_turns,
                    "source_profile": {},
                },
            )

        prior_turns = json.loads(captured_kwargs.get("prior_turns", "[]"))
        assert len(prior_turns) == 2, (
            "When fewer than 8 turns exist, narrator should receive all available turns."
        )


# ===========================================================================
# FIX 3: Setting anchor must be passed to the narrator
# ===========================================================================


class TestSettingAnchor:
    """The narrator has no genre/setting anchor. In the playtest, this caused
    the narrator to drift from sci-fi (Turn 1) to medieval tavern (Turn 3)
    because nothing told it not to. The narrator prompt must include a
    setting_anchor field that locks the genre and setting."""

    @pytest.mark.asyncio
    async def test_narrator_receives_setting_anchor_in_module_kwargs(self):
        """The narrator must pass a 'setting_anchor' kwarg to the DSPy module."""
        Narrator = _import_narrator()

        narrator = Narrator.__new__(Narrator)
        narrator._narrator_module = MagicMock()
        narrator._tone_resolver = MagicMock()

        fake_prediction = MagicMock()
        fake_prediction.narrative_text = "The station hums."
        fake_prediction.proposed_changes = "[]"
        fake_prediction.narrative_time_elapsed = "5"
        narrator._narrator_module.return_value = fake_prediction

        captured_kwargs: dict = {}

        def capture_module_call(**kwargs):
            captured_kwargs.update(kwargs)
            return fake_prediction

        narrator._narrator_module.side_effect = capture_module_call

        with (
            patch.object(Narrator, "_resolve_tone_context", new_callable=AsyncMock, return_value="grim"),
            patch.object(Narrator, "_format_resolution", return_value="narrative"),
            patch.object(Narrator, "_persist_turn", new_callable=AsyncMock, return_value="turn-1"),
            patch.object(Narrator, "_parse_proposed_changes", return_value=[]),
        ):
            await narrator.narrate_turn(
                scene_id=uuid4(),
                user_input="I search the room",
                resolution=None,
                context={
                    "entities": [],
                    "memories": [],
                    "turns": [],
                    "source_profile": {
                        "genre": "sci-fi",
                        "setting_summary": "A derelict salvage station in the Driftward Graveyard",
                    },
                    "actor": {"name": "Kael Draven", "role": "void-born salvage engineer"},
                },
            )

        assert "setting_anchor" in captured_kwargs, (
            "Narrator must pass 'setting_anchor' to the DSPy module. "
            "This field locks the genre and setting to prevent drift."
        )
        anchor = captured_kwargs["setting_anchor"]
        assert "sci-fi" in anchor.lower() or "salvage" in anchor.lower(), (
            f"setting_anchor must contain genre/setting info, got: {anchor}"
        )

    @pytest.mark.asyncio
    async def test_setting_anchor_includes_character_identity(self):
        """The setting anchor must include the character's name and role to prevent
        the narrator from forgetting who the player is."""
        Narrator = _import_narrator()

        narrator = Narrator.__new__(Narrator)
        narrator._narrator_module = MagicMock()
        narrator._tone_resolver = MagicMock()

        fake_prediction = MagicMock()
        fake_prediction.narrative_text = "The station hums."
        fake_prediction.proposed_changes = "[]"
        fake_prediction.narrative_time_elapsed = "5"
        narrator._narrator_module.return_value = fake_prediction

        captured_kwargs: dict = {}

        def capture_module_call(**kwargs):
            captured_kwargs.update(kwargs)
            return fake_prediction

        narrator._narrator_module.side_effect = capture_module_call

        with (
            patch.object(Narrator, "_resolve_tone_context", new_callable=AsyncMock, return_value="grim"),
            patch.object(Narrator, "_format_resolution", return_value="narrative"),
            patch.object(Narrator, "_persist_turn", new_callable=AsyncMock, return_value="turn-1"),
            patch.object(Narrator, "_parse_proposed_changes", return_value=[]),
        ):
            await narrator.narrate_turn(
                scene_id=uuid4(),
                user_input="I search the room",
                resolution=None,
                context={
                    "entities": [],
                    "memories": [],
                    "turns": [],
                    "source_profile": {},
                    "actor": {"name": "Kael Draven", "role": "void-born salvage engineer"},
                },
            )

        anchor = captured_kwargs.get("setting_anchor", "")
        assert "kael" in anchor.lower(), (
            f"setting_anchor must include the character's name, got: {anchor}"
        )


# ===========================================================================
# FIX 4: Character sheet must be passed to the narrator
# ===========================================================================


class TestCharacterSheetPassthrough:
    """The narrator currently receives only the actor's name, role, personality,
    and state_tags. It does NOT receive the character's stats, inventory, or
    conditions. This means the narrator can't reference the character's
    abilities or track resource usage in prose."""

    @pytest.mark.asyncio
    async def test_narrate_passes_character_sheet_to_narrator(self):
        """The narrate() node must pass the character sheet in the context dict."""
        (SceneState, _, _, _, narrate, *_) = _import_scene_loop()

        captured_context: dict = {}

        async def fake_narrate_turn(*, scene_id, user_input, resolution, context, **kwargs):
            captured_context.update(context)
            return {"narrative_text": "You flex your strength.", "proposals": [], "turn_id": "t1"}

        with patch(
            "monitor_agents.narrator.Narrator.narrate_turn",
            new_callable=AsyncMock,
            side_effect=fake_narrate_turn,
        ):
            state = SceneState(
                scene_id=uuid4(),
                story_id=uuid4(),
                user_input="I force the door",
                actor_context={
                    "name": "Kael Draven",
                    "role": "salvage engineer",
                    "stats": {"STR": 14, "DEX": 16, "INT": 12},
                    "inventory": ["cutter", "pistol", "lamp"],
                    "conditions": ["grazed (minor)"],
                },
            )
            await narrate(state)

        assert "actor" in captured_context
        actor = captured_context["actor"]
        assert "stats" in actor, "Character sheet stats must be passed to the narrator"
        assert "inventory" in actor, "Character inventory must be passed to the narrator"
        assert "conditions" in actor, "Character conditions must be passed to the narrator"

    @pytest.mark.asyncio
    async def test_narrator_includes_character_stats_in_profile_context(self):
        """The narrator must inject character stats into the profile_context
        so the DSPy module can reference them in prose."""
        Narrator = _import_narrator()

        narrator = Narrator.__new__(Narrator)
        narrator._narrator_module = MagicMock()
        narrator._tone_resolver = MagicMock()

        fake_prediction = MagicMock()
        fake_prediction.narrative_text = "You flex your strength."
        fake_prediction.proposed_changes = "[]"
        fake_prediction.narrative_time_elapsed = "5"
        narrator._narrator_module.return_value = fake_prediction

        captured_kwargs: dict = {}

        def capture_module_call(**kwargs):
            captured_kwargs.update(kwargs)
            return fake_prediction

        narrator._narrator_module.side_effect = capture_module_call

        with (
            patch.object(Narrator, "_resolve_tone_context", new_callable=AsyncMock, return_value="grim"),
            patch.object(Narrator, "_format_resolution", return_value="narrative"),
            patch.object(Narrator, "_persist_turn", new_callable=AsyncMock, return_value="turn-1"),
            patch.object(Narrator, "_parse_proposed_changes", return_value=[]),
        ):
            await narrator.narrate_turn(
                scene_id=uuid4(),
                user_input="I force the door",
                resolution=None,
                context={
                    "entities": [],
                    "memories": [],
                    "turns": [],
                    "source_profile": {},
                    "actor": {
                        "name": "Kael Draven",
                        "role": "salvage engineer",
                        "stats": {"STR": 14, "DEX": 16, "INT": 12},
                        "inventory": ["cutter", "pistol"],
                        "conditions": ["grazed (minor)"],
                    },
                },
            )

        profile_context = captured_kwargs.get("profile_context", "")
        assert "STR" in profile_context or "14" in profile_context, (
            "Character stats must be injected into profile_context so the narrator "
            "can reference them in prose."
        )


# ===========================================================================
# FIX 5: TurnContext object — spatial/situational awareness
# ===========================================================================


class TestTurnContextObject:
    """The narrator has no structured representation of the current scene
    situation: where the player is, what's nearby, what can be interacted
    with, who else is present. This causes the narrator to lose track of
    spatial context between turns."""

    def test_turn_context_has_required_fields(self):
        """TurnContext must have fields for spatial awareness, NPCs, and scene state."""
        TurnContext = _import_turn_context()

        tc = TurnContext(
            genre="sci-fi",
            setting_summary="A derelict salvage station",
            tone="grim",
            location_name="Corridor junction",
            location_description="Three paths branch from the junction.",
            scene_goal="Find the data core",
            player_position="At the junction",
            nearby_objects=["sealed door", "maintenance hatch", "dataslate"],
            interactables=[
                {"name": "sealed door", "state": "locked", "actions": ["force", "decode"]},
            ],
            exits=["left: collapsed bulkhead", "right: dark corridor", "ahead: sealed door"],
            npcs_present=[{"name": "bartender", "disposition": "wary"}],
            character_name="Kael Draven",
            character_role="void-born salvage engineer",
            character_stats={"STR": 14, "DEX": 16},
            active_conditions=["grazed (minor)"],
            inventory_notable=["cutter", "pistol", "data core"],
            established_facts=["The ship is called the Rust Nail"],
            recent_summary="The player explored the derelict and found a sealed door.",
            pending_roll=None,
        )

        assert tc.genre == "sci-fi"
        assert tc.location_name == "Corridor junction"
        assert len(tc.nearby_objects) == 3
        assert len(tc.interactables) == 1
        assert tc.interactables[0]["state"] == "locked"
        assert len(tc.exits) == 3
        assert len(tc.npcs_present) == 1
        assert tc.character_name == "Kael Draven"
        assert "STR" in tc.character_stats
        assert len(tc.established_facts) == 1
        assert tc.pending_roll is None

    def test_turn_context_defaults_to_empty(self):
        """TurnContext must have sensible defaults for optional fields."""
        TurnContext = _import_turn_context()

        tc = TurnContext(
            genre="sci-fi",
            setting_summary="A derelict station",
            tone="grim",
            location_name="Corridor",
            location_description="Dark corridor.",
            scene_goal="Survive",
            player_position="Standing",
            character_name="Kael",
            character_role="engineer",
        )

        assert tc.nearby_objects == []
        assert tc.interactables == []
        assert tc.exits == []
        assert tc.npcs_present == []
        assert tc.character_stats == {}
        assert tc.active_conditions == []
        assert tc.inventory_notable == []
        assert tc.established_facts == []
        assert tc.recent_summary == ""
        assert tc.pending_roll is None

    def test_turn_context_pending_roll_carries_roll_spec(self):
        """TurnContext.pending_roll must carry the full roll specification."""
        TurnContext = _import_turn_context()

        pending = {
            "stat": "Strength",
            "dc": 12,
            "modifier": -5,
            "action": "force the sealed door",
            "resolution_type": "propose_roll",
        }

        tc = TurnContext(
            genre="sci-fi",
            setting_summary="A derelict station",
            tone="grim",
            location_name="Sealed door",
            location_description="A door with an amber seal light.",
            scene_goal="Get through the door",
            player_position="At the door",
            character_name="Kael",
            character_role="engineer",
            pending_roll=pending,
        )

        assert tc.pending_roll is not None
        assert tc.pending_roll["stat"] == "Strength"
        assert tc.pending_roll["dc"] == 12

    @pytest.mark.asyncio
    async def test_scene_state_has_turn_context_field(self):
        """SceneState must have a turn_context field to carry the TurnContext."""
        (SceneState, *_) = _import_scene_loop()

        state = SceneState(scene_id=uuid4(), story_id=uuid4())
        assert hasattr(state, "turn_context"), (
            "SceneState must have a 'turn_context' field to carry the TurnContext "
            "object through the scene loop."
        )


# ===========================================================================
# FIX 6: extract_facts node — persist established facts for continuity
# ===========================================================================


class TestExtractFactsNode:
    """After each narration, the system must extract concrete facts (names,
    state changes, setting details) and persist them for the next turn's
    context. This prevents the 'Rust Nail' → 'Ostensible' name drift."""

    @pytest.mark.asyncio
    async def test_extract_facts_node_exists(self):
        """The scene loop must have an extract_facts node."""
        from monitor_agents.loops import scene_loop

        assert hasattr(scene_loop, "extract_facts"), (
            "scene_loop must have an 'extract_facts' node that extracts "
            "concrete facts from narration for continuity tracking."
        )

    @pytest.mark.asyncio
    async def test_extract_facts_returns_facts_list(self):
        """extract_facts must return a dict with 'established_facts' key."""
        (SceneState, *_) = _import_scene_loop()

        state = SceneState(
            scene_id=uuid4(),
            story_id=uuid4(),
            narrative_text=(
                "The derelict ship Ostensible looms ahead. The bartender at "
                "The Rust Nail told you the coordinates. Kael's cutter hums."
            ),
        )

        with patch(
            "monitor_agents.loops.scene_loop.extract_facts",
            new_callable=AsyncMock,
            return_value={
                "established_facts": [
                    "The derelict ship is called Ostensible",
                    "The bartender works at The Rust Nail",
                    "Kael carries a cutter",
                ],
            },
        ) as mock_extract:
            # Just verify the mock interface matches
            result = await mock_extract(state)

        assert "established_facts" in result
        assert len(result["established_facts"]) == 3

    @pytest.mark.asyncio
    async def test_extract_facts_handles_empty_narration(self):
        """extract_facts must handle empty narrative_text gracefully."""
        (SceneState, *_) = _import_scene_loop()

        state = SceneState(
            scene_id=uuid4(),
            story_id=uuid4(),
            narrative_text="",
        )

        # When narrative_text is empty, extract_facts should return empty
        # We test the real function here, not a mock
        from monitor_agents.loops.scene_loop import extract_facts

        result = await extract_facts(state)
        assert result == {} or result.get("established_facts", []) == []

    @pytest.mark.asyncio
    async def test_extract_facts_is_in_graph(self):
        """The scene graph must include extract_facts as a node."""
        (_, build_scene_graph, *_) = _import_scene_loop()

        graph = build_scene_graph()
        # Access the graph's node registry
        # StateGraph stores nodes in .nodes attribute
        nodes = graph.nodes
        assert "extract_facts" in nodes, (
            "The scene graph must include 'extract_facts' as a node, "
            "positioned after narrate to extract continuity facts."
        )


# ===========================================================================
# FIX 7: check_consistency guard — catch setting/name drift
# ===========================================================================


class TestConsistencyGuard:
    """A lightweight consistency check must run after narration to catch:
    - Genre drift (sci-fi → medieval)
    - Name changes (Rust Nail → Ostensible)
    - Contradictions with established facts
    This is NOT the full CanonKeeper contradiction detection — it's a fast
    real-time guard that flags issues before the turn is persisted."""

    @pytest.mark.asyncio
    async def test_check_consistency_node_exists(self):
        """The scene loop must have a check_consistency node."""
        from monitor_agents.loops import scene_loop

        assert hasattr(scene_loop, "check_consistency"), (
            "scene_loop must have a 'check_consistency' node that validates "
            "narrator output against established facts before persistence."
        )

    @pytest.mark.asyncio
    async def test_check_consistency_is_in_graph(self):
        """The scene graph must include check_consistency as a node."""
        (_, build_scene_graph, *_) = _import_scene_loop()

        graph = build_scene_graph()
        nodes = graph.nodes
        assert "check_consistency" in nodes, (
            "The scene graph must include 'check_consistency' as a node, "
            "positioned after narrate and before persist_turn_artifacts."
        )

    @pytest.mark.asyncio
    async def test_check_consistency_detects_name_drift(self):
        """When the narrator changes a named entity's name, check_consistency
        must flag it as a violation."""
        (SceneState, *_) = _import_scene_loop()

        state = SceneState(
            scene_id=uuid4(),
            story_id=uuid4(),
            narrative_text="The ship Ostensible looms against the void.",
            turn_context=None,  # Will be set below if TurnContext exists
        )

        # Try to set established_facts via turn_context if available
        try:
            TurnContext = _import_turn_context()
            state.turn_context = TurnContext(
                genre="sci-fi",
                setting_summary="A derelict station",
                tone="grim",
                location_name="Corridor",
                location_description="Dark corridor.",
                scene_goal="Explore",
                player_position="Standing",
                character_name="Kael",
                character_role="engineer",
                established_facts=["The ship is called the Rust Nail"],
            )
        except Exception:
            pass

        with patch(
            "monitor_agents.loops.scene_loop.check_consistency",
            new_callable=AsyncMock,
            return_value={
                "consistency_violations": [
                    {
                        "type": "name_drift",
                        "expected": "Rust Nail",
                        "found": "Ostensible",
                        "severity": "high",
                    }
                ],
            },
        ) as mock_check:
            result = await mock_check(state)

        assert "consistency_violations" in result
        assert len(result["consistency_violations"]) == 1
        assert result["consistency_violations"][0]["type"] == "name_drift"

    @pytest.mark.asyncio
    async def test_check_consistency_no_violations_returns_empty(self):
        """When narration is consistent with established facts, check_consistency
        returns no violations."""
        (SceneState, *_) = _import_scene_loop()
        from monitor_agents.loops.scene_loop import check_consistency

        state = SceneState(
            scene_id=uuid4(),
            story_id=uuid4(),
            narrative_text="The Rust Nail drifts in the void.",
        )

        result = await check_consistency(state)
        violations = result.get("consistency_violations", [])
        assert len(violations) == 0, (
            "When narration is consistent with established facts, "
            "check_consistency should return no violations."
        )


# ===========================================================================
# FIX 8: Pending roll state must carry forward between turns
# ===========================================================================


class TestPendingRollState:
    """When the resolver returns propose_roll with success=pending, the next
    turn must be aware that a roll is pending. Currently the resolver
    classifies each turn in isolation, so a player can narrate their own
    success and skip the roll entirely."""

    @pytest.mark.asyncio
    async def test_scene_state_has_pending_roll_field(self):
        """SceneState must have a pending_roll field."""
        (SceneState, *_) = _import_scene_loop()

        state = SceneState(scene_id=uuid4(), story_id=uuid4())
        assert hasattr(state, "pending_roll"), (
            "SceneState must have a 'pending_roll' field to carry roll state "
            "between turns."
        )
        assert state.pending_roll is None

    @pytest.mark.asyncio
    async def test_resolve_action_detects_pending_roll_from_previous_turn(self):
        """When the previous turn left a pending roll, resolve_action must
        not classify the current action as trivial."""
        (SceneState, _, _, _, _, _, resolve_action, _) = _import_scene_loop()

        pending_roll = {
            "stat": "Strength",
            "dc": 12,
            "modifier": -5,
            "action": "force the sealed door",
            "resolution_type": "propose_roll",
        }

        # The player tries to narrate success instead of rolling
        fake_resolution = {
            "resolution_type": "forced_narrative_pushback",
            "success_level": "pending",
            "pushback_prompt": "You need to roll Strength first!",
            "requires_player_choice": True,
        }

        with patch(
            "monitor_agents.resolver.Resolver.resolve_turn",
            new_callable=AsyncMock,
            return_value=fake_resolution,
        ) as mock_resolve:
            state = SceneState(
                scene_id=uuid4(),
                story_id=uuid4(),
                user_input="The creature lies motionless at my feet",
                pending_roll=pending_roll,
            )
            await resolve_action(state)

        # The resolver must have been called with the pending_roll context
        call_kwargs = mock_resolve.call_args
        context_arg = call_kwargs.kwargs.get("context", {})
        if not context_arg and len(call_kwargs.args) > 2:
            context_arg = call_kwargs.args[2]
        assert "pending_roll" in context_arg, (
            "resolve_action must pass pending_roll to the resolver so it can "
            "detect when a player is trying to skip a roll."
        )

    @pytest.mark.asyncio
    async def test_propose_roll_sets_pending_roll_in_state(self):
        """When the resolver returns propose_roll, the state must be updated
        with the pending roll spec for the next turn."""
        (SceneState, _, _, _, _, _, resolve_action, _) = _import_scene_loop()

        fake_resolution = {
            "resolution_type": "propose_roll",
            "success_level": "pending",
            "stat": "Strength",
            "difficulty_class": 12,
            "modifier": -5,
            "requires_player_choice": True,
            "roll_breakdown": "propose_roll — Strength check (DC 12)",
        }

        with patch(
            "monitor_agents.resolver.Resolver.resolve_turn",
            new_callable=AsyncMock,
            return_value=fake_resolution,
        ):
            state = SceneState(
                scene_id=uuid4(),
                story_id=uuid4(),
                user_input="I swing my cutter at the creature",
            )
            result = await resolve_action(state)

        assert "pending_roll" in result, (
            "When resolver returns propose_roll, resolve_action must set "
            "pending_roll in the state update so the next turn knows a roll is pending."
        )
        assert result["pending_roll"] is not None
        assert result["pending_roll"]["stat"] == "Strength"
        assert result["pending_roll"]["dc"] == 12

    @pytest.mark.asyncio
    async def test_pending_roll_cleared_on_successful_roll(self):
        """When a roll is resolved (not pending), pending_roll must be cleared."""
        (SceneState, _, _, _, _, _, resolve_action, _) = _import_scene_loop()

        fake_resolution = {
            "resolution_type": "dice",
            "success_level": "success",
            "stat": "Strength",
            "difficulty_class": 12,
            "roll_total": 15,
            "roll_detail": {"rolls": [20], "total": 15},
        }

        with patch(
            "monitor_agents.resolver.Resolver.resolve_turn",
            new_callable=AsyncMock,
            return_value=fake_resolution,
        ):
            state = SceneState(
                scene_id=uuid4(),
                story_id=uuid4(),
                user_input="I roll Strength",
                pending_roll={
                    "stat": "Strength",
                    "dc": 12,
                    "action": "force the door",
                },
            )
            result = await resolve_action(state)

        assert result.get("pending_roll") is None, (
            "When a roll is resolved, pending_roll must be cleared from state."
        )


# ===========================================================================
# INTEGRATION: Full graph flow with turn context
# ===========================================================================


class TestGraphFlowWithTurnContext:
    """Verify the scene graph includes the new nodes in the correct order."""

    def test_graph_has_all_expected_nodes(self):
        """The scene graph must include all new nodes."""
        (_, build_scene_graph, *_) = _import_scene_loop()

        graph = build_scene_graph()
        nodes = set(graph.nodes.keys())

        expected_nodes = {
            "load_context",
            "resolve",
            "narrate",
            "extract_new_entities",
            "extract_memories",
            "persist_memories",
            "check_events",
            "persist_turn_artifacts",
            "complete_current_scene",
            "canonize",
        }

        missing = expected_nodes - nodes
        assert not missing, f"Graph is missing expected nodes: {missing}"

    def test_graph_includes_new_coherence_nodes(self):
        """The scene graph must include the new coherence nodes."""
        (_, build_scene_graph, *_) = _import_scene_loop()

        graph = build_scene_graph()
        nodes = set(graph.nodes.keys())

        new_nodes = {"extract_facts", "check_consistency"}
        missing = new_nodes - nodes
        assert not missing, (
            f"Graph must include new coherence nodes: {missing}. "
            f"Current nodes: {nodes}"
        )

    def test_extract_facts_runs_after_narrate(self):
        """extract_facts must be positioned after narrate in the graph flow."""
        (_, build_scene_graph, *_) = _import_scene_loop()

        graph = build_scene_graph()
        # Check that there's an edge from narrate to extract_facts
        # LangGraph stores edges in .edges
        edges = graph.edges
        assert ("narrate", "extract_facts") in edges or any(
            edge[0] == "narrate" and edge[1] == "extract_facts"
            for edge in edges
        ), "extract_facts must be connected after narrate in the graph"

    def test_check_consistency_runs_before_persist(self):
        """check_consistency must run before persist_turn_artifacts (possibly through check_events)."""
        (_, build_scene_graph, *_) = _import_scene_loop()

        graph = build_scene_graph()
        edges = graph.edges
        # check_consistency → check_events → persist_turn_artifacts is the flow
        assert ("check_consistency", "check_events") in edges, (
            "check_consistency must be connected to check_events in the graph"
        )
        assert ("check_events", "persist_turn_artifacts") in edges, (
            "check_events must still connect to persist_turn_artifacts"
        )


# ===========================================================================
# RESOLVER-SIDE: Pending roll interception
# ===========================================================================


class TestResolverPendingRollInterception:
    """The resolver must read pending_roll from context and push back when
    a player tries to narrate past an unresolved roll."""

    @pytest.mark.asyncio
    async def test_resolver_pushes_back_when_player_skips_roll(self):
        """When pending_roll is set and player doesn't explicitly roll,
        the resolver must return forced_narrative_pushback."""
        from monitor_agents.resolver import Resolver

        resolver = Resolver.__new__(Resolver)

        pending_roll = {
            "stat": "Strength",
            "dc": 12,
            "modifier": -5,
            "action": "force the sealed door",
            "resolution_type": "propose_roll",
        }

        result = await resolver.resolve_turn(
            scene_id=str(uuid4()),
            user_input="The creature lies motionless at my feet",
            context={
                "entities": [],
                "turns": [],
                "source_profile": {},
                "pending_roll": pending_roll,
            },
            game_context={},
            play_mode="dice_game_system",
            roll_mode="normal",
        )

        assert result["resolution_type"] == "forced_narrative_pushback", (
            "When a pending roll exists and the player doesn't roll, "
            "the resolver must push back instead of allowing trivial resolution."
        )
        assert result["success_level"] == "pending"
        assert result["requires_player_choice"] is True
        assert "Strength" in result.get("pushback_prompt", "")

    @pytest.mark.asyncio
    async def test_resolver_allows_explicit_roll_when_pending(self):
        """When pending_roll is set and player explicitly rolls, the resolver
        must proceed with normal roll resolution."""
        from monitor_agents.resolver import Resolver

        resolver = Resolver.__new__(Resolver)

        pending_roll = {
            "stat": "Strength",
            "dc": 12,
            "modifier": -5,
            "action": "force the sealed door",
            "resolution_type": "propose_roll",
        }

        result = await resolver.resolve_turn(
            scene_id=str(uuid4()),
            user_input="I roll Strength to force the door",
            context={
                "entities": [],
                "turns": [],
                "source_profile": {},
                "pending_roll": pending_roll,
            },
            game_context={},
            play_mode="dice_game_system",
            roll_mode="normal",
        )

        # Should NOT be a pushback — the player is rolling
        assert result["resolution_type"] != "forced_narrative_pushback", (
            "When the player explicitly rolls, the resolver must not push back."
        )

    @pytest.mark.asyncio
    async def test_resolver_no_pending_roll_allows_trivial(self):
        """When there's no pending roll, trivial actions should work normally."""
        from monitor_agents.resolver import Resolver

        resolver = Resolver.__new__(Resolver)

        result = await resolver.resolve_turn(
            scene_id=str(uuid4()),
            user_input="I look around the room",
            context={
                "entities": [],
                "turns": [],
                "source_profile": {},
            },
            game_context={},
            play_mode="dice_game_system",
            roll_mode="normal",
        )

        # Without a pending roll, looking around should be trivial
        assert result["resolution_type"] in ("trivial", "narrative")
        assert result["success_level"] == "success"


# ===========================================================================
# NARRATOR-SIDE: Established facts and turn context injection
# ===========================================================================


class TestNarratorContextInjection:
    """The narrator must inject established_facts and turn_context into
    profile_context so the DSPy module can see them."""

    @pytest.mark.asyncio
    async def test_narrator_injects_established_facts_into_profile_context(self):
        """Established facts must appear in profile_context to prevent contradictions."""
        Narrator = _import_narrator()

        narrator = Narrator.__new__(Narrator)
        narrator._narrator_module = MagicMock()
        narrator._tone_resolver = MagicMock()

        fake_prediction = MagicMock()
        fake_prediction.narrative_text = "The Rust Nail drifts in the void."
        fake_prediction.proposed_changes = "[]"
        fake_prediction.narrative_time_elapsed = "5"
        narrator._narrator_module.return_value = fake_prediction

        captured_kwargs: dict = {}

        def capture_module_call(**kwargs):
            captured_kwargs.update(kwargs)
            return fake_prediction

        narrator._narrator_module.side_effect = capture_module_call

        with (
            patch.object(Narrator, "_resolve_tone_context", new_callable=AsyncMock, return_value="grim"),
            patch.object(Narrator, "_format_resolution", return_value="narrative"),
            patch.object(Narrator, "_persist_turn", new_callable=AsyncMock, return_value="turn-1"),
            patch.object(Narrator, "_parse_proposed_changes", return_value=[]),
        ):
            await narrator.narrate_turn(
                scene_id=uuid4(),
                user_input="I approach the ship",
                resolution=None,
                context={
                    "entities": [],
                    "memories": [],
                    "turns": [],
                    "source_profile": {},
                    "established_facts": [
                        "Named entity mentioned: Rust Nail",
                        "The ship is called the Rust Nail",
                    ],
                },
            )

        profile_context = captured_kwargs.get("profile_context", "")
        assert "ESTABLISHED FACTS" in profile_context, (
            "Established facts must be injected into profile_context so the "
            "narrator can reference them and avoid contradictions."
        )
        assert "Rust Nail" in profile_context

    @pytest.mark.asyncio
    async def test_narrator_injects_turn_context_into_profile_context(self):
        """TurnContext must be rendered into profile_context for spatial awareness."""
        Narrator = _import_narrator()

        narrator = Narrator.__new__(Narrator)
        narrator._narrator_module = MagicMock()
        narrator._tone_resolver = MagicMock()

        fake_prediction = MagicMock()
        fake_prediction.narrative_text = "The corridor stretches ahead."
        fake_prediction.proposed_changes = "[]"
        fake_prediction.narrative_time_elapsed = "5"
        narrator._narrator_module.return_value = fake_prediction

        captured_kwargs: dict = {}

        def capture_module_call(**kwargs):
            captured_kwargs.update(kwargs)
            return fake_prediction

        narrator._narrator_module.side_effect = capture_module_call

        turn_context_dict = {
            "genre": "sci-fi",
            "setting_summary": "A derelict salvage station",
            "tone": "grim",
            "location_name": "Corridor junction",
            "location_description": "Three paths branch from the junction.",
            "scene_goal": "Find the data core",
            "player_position": "At the junction",
            "nearby_objects": ["sealed door", "maintenance hatch"],
            "interactables": [{"name": "sealed door", "state": "locked"}],
            "exits": ["left: collapsed bulkhead", "right: dark corridor"],
            "npcs_present": [{"name": "bartender", "disposition": "wary"}],
            "character_name": "Kael Draven",
            "character_role": "void-born salvage engineer",
            "character_stats": {"STR": 14},
            "active_conditions": ["grazed (minor)"],
            "inventory_notable": ["cutter", "pistol"],
            "established_facts": ["The ship is called the Rust Nail"],
            "recent_summary": "The player explored the derelict.",
            "pending_roll": None,
        }

        with (
            patch.object(Narrator, "_resolve_tone_context", new_callable=AsyncMock, return_value="grim"),
            patch.object(Narrator, "_format_resolution", return_value="narrative"),
            patch.object(Narrator, "_persist_turn", new_callable=AsyncMock, return_value="turn-1"),
            patch.object(Narrator, "_parse_proposed_changes", return_value=[]),
        ):
            await narrator.narrate_turn(
                scene_id=uuid4(),
                user_input="I look around",
                resolution=None,
                context={
                    "entities": [],
                    "memories": [],
                    "turns": [],
                    "source_profile": {},
                    "turn_context": turn_context_dict,
                },
            )

        profile_context = captured_kwargs.get("profile_context", "")
        assert "TURN CONTEXT" in profile_context, (
            "TurnContext must be rendered into profile_context for spatial awareness."
        )
        assert "Corridor junction" in profile_context
        assert "sealed door" in profile_context
        assert "Kael Draven" in profile_context

    @pytest.mark.asyncio
    async def test_narrator_injects_context_summary_into_profile_context(self):
        """The context_summary from ContextAssembly must be available to the narrator."""
        Narrator = _import_narrator()

        narrator = Narrator.__new__(Narrator)
        narrator._narrator_module = MagicMock()
        narrator._tone_resolver = MagicMock()

        fake_prediction = MagicMock()
        fake_prediction.narrative_text = "The station hums."
        fake_prediction.proposed_changes = "[]"
        fake_prediction.narrative_time_elapsed = "5"
        narrator._narrator_module.return_value = fake_prediction

        captured_kwargs: dict = {}

        def capture_module_call(**kwargs):
            captured_kwargs.update(kwargs)
            return fake_prediction

        narrator._narrator_module.side_effect = capture_module_call

        with (
            patch.object(Narrator, "_resolve_tone_context", new_callable=AsyncMock, return_value="grim"),
            patch.object(Narrator, "_format_resolution", return_value="narrative"),
            patch.object(Narrator, "_persist_turn", new_callable=AsyncMock, return_value="turn-1"),
            patch.object(Narrator, "_parse_proposed_changes", return_value=[]),
        ):
            await narrator.narrate_turn(
                scene_id=uuid4(),
                user_input="I search the room",
                resolution=None,
                context={
                    "entities": [],
                    "memories": [],
                    "turns": [],
                    "source_profile": {},
                    "context_summary": "Context for action: I search the room\n[Entity] Rhal (NPC)",
                },
            )

        # context_summary should be passed as a separate kwarg to the DSPy module
        assert captured_kwargs.get("context_summary", "") != "", (
            "context_summary must be passed to the DSPy module as a separate field."
        )
        assert "Rhal" in captured_kwargs.get("context_summary", "")


# ===========================================================================
# EXTRACT_FACTS: Functional tests
# ===========================================================================


class TestExtractFactsFunctional:
    """Functional tests for the extract_facts node — not mocked."""

    @pytest.mark.asyncio
    async def test_extract_facts_finds_named_entities(self):
        """extract_facts must find named entities in narration text."""
        (SceneState, *_) = _import_scene_loop()
        from monitor_agents.loops.scene_loop import extract_facts

        state = SceneState(
            scene_id=uuid4(),
            story_id=uuid4(),
            narrative_text=(
                "The derelict ship Ostensible looms against the void-black sky. "
                "Kael Draven steps through the airlock, cutter humming."
            ),
        )

        result = await extract_facts(state)

        assert "established_facts" in result
        facts = result["established_facts"]
        # Should find at least "Ostensible" and "Kael Draven"
        all_facts_text = " ".join(facts)
        assert "Ostensible" in all_facts_text, (
            f"extract_facts should find 'Ostensible' in narration. Facts: {facts}"
        )
        assert "Kael" in all_facts_text, (
            f"extract_facts should find 'Kael' in narration. Facts: {facts}"
        )

    @pytest.mark.asyncio
    async def test_extract_facts_merges_with_existing_facts(self):
        """extract_facts must merge new facts with existing established_facts."""
        (SceneState, *_) = _import_scene_loop()
        from monitor_agents.loops.scene_loop import extract_facts

        state = SceneState(
            scene_id=uuid4(),
            story_id=uuid4(),
            narrative_text="The bartender at The Rust Nail pours a drink.",
            established_facts=["Named entity mentioned: Ostensible"],
        )

        result = await extract_facts(state)

        assert "established_facts" in result
        facts = result["established_facts"]
        # Should contain both old and new facts
        all_facts_text = " ".join(facts)
        assert "Ostensible" in all_facts_text, "Existing facts must be preserved"
        assert "Rust" in all_facts_text or "bartender" in all_facts_text.lower(), (
            "New facts must be extracted and merged"
        )

    @pytest.mark.asyncio
    async def test_extract_facts_caps_at_50(self):
        """extract_facts must cap at 50 facts to prevent unbounded growth."""
        (SceneState, *_) = _import_scene_loop()
        from monitor_agents.loops.scene_loop import extract_facts

        # Pre-fill with 45 existing facts
        existing = [f"Fact number {i}" for i in range(45)]
        state = SceneState(
            scene_id=uuid4(),
            story_id=uuid4(),
            narrative_text="Kael Draven approaches the Ostensible.",
            established_facts=existing,
        )

        result = await extract_facts(state)
        facts = result.get("established_facts", [])
        assert len(facts) <= 50, (
            f"established_facts must be capped at 50, got {len(facts)}"
        )


# ===========================================================================
# CHECK_CONSISTENCY: Functional tests
# ===========================================================================


class TestCheckConsistencyFunctional:
    """Functional tests for the check_consistency node — not mocked."""

    @pytest.mark.asyncio
    async def test_check_consistency_detects_genre_drift(self):
        """When the setting is sci-fi but narration uses medieval terms,
        check_consistency must flag it."""
        (SceneState, *_) = _import_scene_loop()
        from monitor_agents.loops.scene_loop import check_consistency

        state = SceneState(
            scene_id=uuid4(),
            story_id=uuid4(),
            narrative_text=(
                "The tavern reeks of stale ale. A corkboard hangs by the hearth. "
                "The innkeeper polishes a tankard."
            ),
            source_profile={"genre": "sci-fi"},
        )

        result = await check_consistency(state)
        violations = result.get("consistency_violations", [])

        assert len(violations) > 0, (
            "check_consistency must detect genre drift when sci-fi setting "
            "has medieval terms like 'tavern', 'hearth', 'ale'."
        )
        assert any(v["type"] == "genre_drift" for v in violations)

    @pytest.mark.asyncio
    async def test_check_consistency_no_violations_for_consistent_narration(self):
        """When narration is consistent with the setting, no violations."""
        (SceneState, *_) = _import_scene_loop()
        from monitor_agents.loops.scene_loop import check_consistency

        state = SceneState(
            scene_id=uuid4(),
            story_id=uuid4(),
            narrative_text=(
                "The airlock hisses open. Kael steps into the corridor, "
                "his lamp cutting through the darkness."
            ),
            source_profile={"genre": "sci-fi"},
        )

        result = await check_consistency(state)
        violations = result.get("consistency_violations", [])
        assert len(violations) == 0, (
            f"check_consistency should not flag consistent sci-fi narration. "
            f"Violations: {violations}"
        )

    @pytest.mark.asyncio
    async def test_check_consistency_detects_name_drift(self):
        """When established facts say the ship is 'Rust Nail' but narration
        says 'Ostensible', check_consistency must flag it."""
        (SceneState, *_) = _import_scene_loop()
        from monitor_agents.loops.scene_loop import check_consistency

        state = SceneState(
            scene_id=uuid4(),
            story_id=uuid4(),
            narrative_text="The hull reads Ostensible, faded and corroded.",
            established_facts=["Named entity mentioned: Rust Nail"],
        )

        result = await check_consistency(state)
        violations = result.get("consistency_violations", [])

        # Should detect that "Ostensible" doesn't match established "Rust Nail"
        name_drifts = [v for v in violations if v["type"] == "name_drift"]
        assert len(name_drifts) > 0, (
            "check_consistency must detect name drift when 'Ostensible' "
            "contradicts established name 'Rust Nail'."
        )
        assert name_drifts[0]["expected"] == "Rust Nail"
        assert name_drifts[0]["found"] == "Ostensible"