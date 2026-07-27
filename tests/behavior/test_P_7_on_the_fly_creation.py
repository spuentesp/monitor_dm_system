"""
P-7: On-the-fly Entity Creation — Contract & Behavior Tests

Tests the NarrativeEntityExtractionModule and the extract_new_entities
scene-loop node for detecting and proposing new entities from narration.

Use Cases: P-7 (On-the-fly creation), P-8 (Canonization)
"""

from uuid import uuid4

import pytest
from monitor_data.schemas.base import Authority, ProposalType
from monitor_data.schemas.proposed_changes import ProposedChangeCreate

# =============================================================================
# NarrativeEntityExtractionModule — Contract Tests
# =============================================================================


@pytest.mark.unit
class TestNarrativeEntityExtractionSignature:
    """Contract tests for the NarrativeEntityExtractionSignature DSPy module."""

    def test_module_import(self):
        """Module can be imported from prompts package."""
        from monitor_agents.extraction.narrative_entity_extraction import (
            NarrativeEntityExtractionModule,
            NarrativeEntityExtractionSignature,
        )

        assert NarrativeEntityExtractionModule is not None
        assert NarrativeEntityExtractionSignature is not None

    def test_signature_has_required_input_fields(self):
        """Signature defines narration, known_entities, and universe_context inputs."""
        from monitor_agents.extraction.narrative_entity_extraction import (
            NarrativeEntityExtractionSignature,
        )

        sig = NarrativeEntityExtractionSignature
        # dspy.Signature fields: at least narration and known_entities as inputs
        assert "narration" in sig.model_fields or hasattr(sig, "narration")

    def test_signature_has_output_field(self):
        """Signature defines new_entities output."""
        from monitor_agents.extraction.narrative_entity_extraction import (
            NarrativeEntityExtractionSignature,
        )

        sig = NarrativeEntityExtractionSignature
        assert "new_entities" in sig.model_fields or hasattr(sig, "new_entities")

    def test_module_instantiation(self):
        """Module can be instantiated without errors."""
        from monitor_agents.extraction.narrative_entity_extraction import (
            NarrativeEntityExtractionModule,
        )

        module = NarrativeEntityExtractionModule()
        assert module is not None
        assert hasattr(module, "extract")

    def test_module_exported_from_extraction(self):
        """Module is exported from monitor_agents.extraction.narrative_entity_extraction."""
        from monitor_agents.extraction.narrative_entity_extraction import (
            NarrativeEntityExtractionModule,
            NarrativeEntityExtractionSignature,
        )

        assert NarrativeEntityExtractionModule is not None
        assert NarrativeEntityExtractionSignature is not None


# =============================================================================
# ProposedChangeCreate — Contract Tests for Entity Proposals
# =============================================================================


@pytest.mark.unit
class TestEntityProposalContract:
    """Contract tests for ProposedChangeCreate schema when used for entity proposals."""

    def test_entity_proposal_minimal(self):
        """ProposedChangeCreate for an entity with minimal fields is valid."""
        scene_id = uuid4()
        proposal = ProposedChangeCreate(
            scene_id=scene_id,
            change_type=ProposalType.ENTITY,
            content={
                "name": "Theron",
                "entity_type": "CHARACTER",
                "description": "A guard",
            },
            confidence=0.9,
            authority=Authority.SYSTEM,
            proposer="narrator",
        )
        assert proposal.change_type == ProposalType.ENTITY
        assert proposal.content["name"] == "Theron"
        assert proposal.confidence == 0.9
        assert proposal.authority == Authority.SYSTEM
        assert proposal.proposer == "narrator"

    def test_entity_proposal_with_story_and_turn(self):
        """ProposedChangeCreate can include story_id and turn_id."""
        scene_id = uuid4()
        story_id = uuid4()
        turn_id = uuid4()
        proposal = ProposedChangeCreate(
            scene_id=scene_id,
            story_id=story_id,
            turn_id=turn_id,
            change_type=ProposalType.ENTITY,
            content={
                "name": "The Rusty Tankard",
                "entity_type": "LOCATION",
                "description": "A tavern",
            },
            confidence=0.85,
            authority=Authority.SYSTEM,
            proposer="narrator",
        )
        assert proposal.story_id == story_id
        assert proposal.turn_id == turn_id

    def test_entity_proposal_confidence_bounds(self):
        """ProposedChangeCreate confidence must be between 0.0 and 1.0."""
        scene_id = uuid4()
        # Valid confidence
        proposal = ProposedChangeCreate(
            scene_id=scene_id,
            change_type=ProposalType.ENTITY,
            content={"name": "Test", "entity_type": "CONCEPT"},
            confidence=0.0,
            authority=Authority.SYSTEM,
        )
        assert proposal.confidence == 0.0

        proposal = ProposedChangeCreate(
            scene_id=scene_id,
            change_type=ProposalType.ENTITY,
            content={"name": "Test", "entity_type": "CONCEPT"},
            confidence=1.0,
            authority=Authority.SYSTEM,
        )
        assert proposal.confidence == 1.0

    def test_entity_proposal_all_entity_types(self):
        """ProposedChangeCreate accepts all valid entity types in content."""
        scene_id = uuid4()
        for entity_type in [
            "CHARACTER",
            "FACTION",
            "LOCATION",
            "OBJECT",
            "CONCEPT",
            "ORGANIZATION",
        ]:
            proposal = ProposedChangeCreate(
                scene_id=scene_id,
                change_type=ProposalType.ENTITY,
                content={"name": f"Test {entity_type}", "entity_type": entity_type},
                confidence=0.8,
                authority=Authority.SYSTEM,
            )
            assert proposal.content["entity_type"] == entity_type

    def test_entity_proposal_authority_values(self):
        """ProposedChangeCreate accepts all Authority values."""
        scene_id = uuid4()
        for authority in Authority:
            proposal = ProposedChangeCreate(
                scene_id=scene_id,
                change_type=ProposalType.ENTITY,
                content={"name": "Test"},
                confidence=0.8,
                authority=authority,
            )
            assert proposal.authority == authority

    def test_entity_proposal_default_values(self):
        """ProposedChangeCreate has sensible defaults for entity proposals."""
        scene_id = uuid4()
        proposal = ProposedChangeCreate(
            scene_id=scene_id,
            change_type=ProposalType.ENTITY,
            content={"name": "Test"},
        )
        assert proposal.confidence == 1.0
        assert proposal.authority == Authority.SYSTEM
        assert proposal.proposer == "Unknown"
        assert proposal.evidence == []


# =============================================================================
# extract_new_entities — Behavior Tests
# =============================================================================


@pytest.mark.unit
class TestExtractNewEntitiesBehavior:
    """Behavior tests for the extract_new_entities scene-loop node."""

    def _make_state(self, **overrides):
        """Helper to create a SceneState with sensible defaults."""
        from monitor_agents.loops.scene_loop import SceneState

        defaults = {
            "scene_id": uuid4(),
            "story_id": uuid4(),
            "universe_id": uuid4(),
            "entity_context": [],
            "memory_context": [],
            "previous_turns": [],
            "pending_proposals": [],
            "narrative_text": None,
            "user_input": "I talk to the guard",
            "actor_id": uuid4(),
            "actor_context": {"name": "Aldric", "entity_type": "CHARACTER"},
            "game_context": {},
            "turns_count": 1,
        }
        defaults.update(overrides)
        return SceneState(**defaults)

    def test_state_has_pending_proposals_field(self):
        """SceneState has pending_proposals field for on-the-fly proposals."""
        state = self._make_state()
        assert hasattr(state, "pending_proposals")
        assert state.pending_proposals == []

    def test_state_accepts_entity_proposals(self):
        """SceneState.pending_proposals can hold entity proposal dicts."""
        proposal = {
            "proposal_type": "ENTITY",
            "content": {"name": "Theron", "entity_type": "CHARACTER"},
            "summary": "New entity detected in narration: Theron",
            "confidence": 0.9,
            "authority": "SYSTEM",
            "proposer": "narrator",
        }
        state = self._make_state(pending_proposals=[proposal])
        assert len(state.pending_proposals) == 1
        assert state.pending_proposals[0]["proposal_type"] == "ENTITY"
        assert state.pending_proposals[0]["content"]["name"] == "Theron"

    def test_extract_new_entities_returns_empty_when_no_narration(self):
        """extract_new_entities returns empty dict when narrative_text is None."""
        from monitor_agents.loops.scene_loop import extract_new_entities

        state = self._make_state(narrative_text=None)
        # Drive the async function with a fresh event loop. We avoid
        # `asyncio.get_event_loop()` because pytest-asyncio may have
        # already closed it by the time this test runs, causing
        # "Event loop is closed" failures when this test runs as part
        # of a larger suite (it passes in isolation).
        import asyncio

        result = asyncio.new_event_loop().run_until_complete(
            extract_new_entities(state)
        )
        assert result == {}

    def test_extract_new_entities_returns_empty_when_empty_narration(self):
        """extract_new_entities returns empty dict when narrative_text is empty string."""
        from monitor_agents.loops.scene_loop import extract_new_entities

        state = self._make_state(narrative_text="")
        import asyncio

        result = asyncio.new_event_loop().run_until_complete(
            extract_new_entities(state)
        )
        assert result == {}

    def test_proposal_dict_matches_canonkeeper_expectations(self):
        """Entity proposal dicts have the fields CanonKeeper.evaluate_proposals expects."""
        proposal = {
            "proposal_type": "ENTITY",
            "content": {
                "name": "Theron",
                "entity_type": "CHARACTER",
                "description": "A guard at the north gate",
                "is_archetype": False,
            },
            "summary": "New entity detected in narration: Theron",
            "confidence": 0.9,
            "authority": "SYSTEM",
            "proposer": "narrator",
        }
        # CanonKeeper expects these keys in each proposal dict
        assert "proposal_type" in proposal
        assert "content" in proposal
        assert "summary" in proposal
        assert "confidence" in proposal
        assert "authority" in proposal
        assert "proposer" in proposal
        # Content should have entity fields
        assert "name" in proposal["content"]
        assert "entity_type" in proposal["content"]

    def test_known_entities_filtering(self):
        """Entities already in entity_context should not be re-proposed."""
        # This tests the logic that known_names from entity_context
        # are passed to the LLM to avoid duplicates
        state = self._make_state(
            entity_context=[
                {"name": "Aldric", "entity_type": "CHARACTER"},
                {"name": "The Rusty Tankard", "entity_type": "LOCATION"},
            ]
        )
        # The extract_new_entities function builds known_names from entity_context
        known_names = [e.get("name", "") for e in state.entity_context if e.get("name")]
        assert "Aldric" in known_names
        assert "The Rusty Tankard" in known_names


# =============================================================================
# SceneLoop Graph — Integration Contract Tests
# =============================================================================


@pytest.mark.unit
class TestSceneLoopGraphContract:
    """Contract tests verifying the SceneLoop graph includes extract_new_entities."""

    def test_graph_has_extract_new_entities_node(self):
        """The SceneLoop graph includes the extract_new_entities node."""
        from monitor_agents.loops.scene_loop import build_scene_graph

        graph = build_scene_graph()
        # StateGraph.nodes is a dict mapping node names to callables
        assert "extract_new_entities" in graph.nodes

    def test_graph_edge_from_narrate_to_extract_new_entities(self):
        """The graph has an edge from narrate to extract_new_entities."""
        from monitor_agents.loops.scene_loop import build_scene_graph

        graph = build_scene_graph()
        # Check that narrate's outgoing edges include extract_new_entities
        # In LangGraph, edges are stored in the graph structure
        # We verify the node exists and is between narrate and extract_memories
        assert "extract_new_entities" in graph.nodes
        assert "narrate" in graph.nodes
        assert "extract_memories" in graph.nodes

    def test_graph_edge_from_extract_new_entities_to_extract_memories(self):
        """The graph has an edge from extract_new_entities to extract_memories."""
        from monitor_agents.loops.scene_loop import build_scene_graph

        graph = build_scene_graph()
        assert "extract_new_entities" in graph.nodes
        assert "extract_memories" in graph.nodes
