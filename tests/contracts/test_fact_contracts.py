"""
Tests for fact contracts.

Use Cases: DL-3, DL-13
"""

import pytest
from datetime import datetime, timezone
from uuid import uuid4
from typing import Optional, List

from monitor_data.schemas.base import CanonLevel, KnowledgeScope, Authority
from monitor_data.schemas.facts import FactCreate, FactUpdate, FactResponse, FactType
from monitor_data.contracts.fact_contracts import (
    FactPreConditions,
    FactPostConditions,
    FactInvariants,
)


def _make_fact_response(**overrides) -> FactResponse:
    """Helper to create a valid FactResponse with required fields."""
    defaults = {
        'id': uuid4(),
        'universe_id': uuid4(),
        'statement': 'The sky is blue.',
        'fact_type': FactType.STATE,
        'canon_level': CanonLevel.CANON,
        'knowledge_scope': KnowledgeScope.WORLD,
        'confidence': 1.0,
        'authority': Authority.GM,
        'status': 'active',
        'created_at': datetime.now(timezone.utc),
        'replaces': None,
        'properties': {},
    }
    defaults.update(overrides)
    return FactResponse(**defaults)


class TestFactPreConditions:
    """Tests for Fact pre-conditions."""

    def test_create_fact_preconditions_valid(self):
        """Valid fact creation passes pre-conditions."""
        params = FactCreate(
            universe_id=uuid4(),
            statement="The sky is blue.",
            fact_type=FactType.STATE,
            canon_level=CanonLevel.CANON,
            knowledge_scope=KnowledgeScope.WORLD,
        )
        
        assert FactPreConditions.create_fact(
            params,
            universe_exists=True,
            caller_is_canon_keeper=True,
        ) is True

    def test_create_fact_preconditions_unauthorized(self):
        """Fact creation fails if not CanonKeeper."""
        params = FactCreate(
            universe_id=uuid4(),
            statement="The sky is blue.",
            fact_type=FactType.STATE,
            canon_level=CanonLevel.CANON,
            knowledge_scope=KnowledgeScope.WORLD,
        )
        
        with pytest.raises(PermissionError, match="Only CanonKeeper can create facts"):
            FactPreConditions.create_fact(
                params,
                universe_exists=True,
                caller_is_canon_keeper=False,
            )

    def test_create_fact_preconditions_missing_universe(self):
        """Fact creation fails if universe doesn't exist."""
        params = FactCreate(
            universe_id=uuid4(),
            statement="The sky is blue.",
            fact_type=FactType.STATE,
            canon_level=CanonLevel.CANON,
            knowledge_scope=KnowledgeScope.WORLD,
        )
        
        with pytest.raises(ValueError, match="Universe .* does not exist"):
            FactPreConditions.create_fact(
                params,
                universe_exists=False,
                caller_is_canon_keeper=True,
            )

    def test_update_fact_valid_transition(self):
        """Valid canon_level transition passes pre-conditions."""
        current_fact = _make_fact_response(
            canon_level=CanonLevel.PROPOSED,
            confidence=0.5,
        )
        
        assert FactPreConditions.update_fact(
            current_fact,
            new_canon_level=CanonLevel.CANON,
            caller_is_canon_keeper=True,
        ) is True

    def test_update_fact_invalid_transition(self):
        """Invalid canon_level transition fails pre-conditions."""
        current_fact = _make_fact_response(
            canon_level=CanonLevel.CANON,
            confidence=1.0,
        )
        
        # CANON to PROPOSED is invalid (backwards transition)
        with pytest.raises(ValueError, match="Invalid canon_level transition"):
            FactPreConditions.update_fact(
                current_fact,
                new_canon_level=CanonLevel.PROPOSED,
                caller_is_canon_keeper=True,
            )


class TestFactPostConditions:
    """Tests for Fact post-conditions."""

    def test_create_fact_postconditions(self):
        """Fact creation satisfies post-conditions."""
        params = FactCreate(
            universe_id=uuid4(),
            statement="The sky is blue.",
            fact_type=FactType.STATE,
            canon_level=CanonLevel.CANON,
            knowledge_scope=KnowledgeScope.WORLD,
        )
        
        result = _make_fact_response(
            universe_id=params.universe_id,
            statement=params.statement,
            fact_type=params.fact_type,
            canon_level=params.canon_level,
            confidence=1.0,
        )
        
        assert FactPostConditions.create_fact(result, params) is True

    def test_create_fact_postconditions_wrong_universe(self):
        """Fact creation fails if universe_id mismatch."""
        params = FactCreate(
            universe_id=uuid4(),
            statement="The sky is blue.",
            fact_type=FactType.STATE,
            canon_level=CanonLevel.CANON,
            knowledge_scope=KnowledgeScope.WORLD,
        )
        
        wrong_result = _make_fact_response(
            universe_id=uuid4(),  # Different universe
        )
        
        with pytest.raises(ValueError, match="universe_id mismatch"):
            FactPostConditions.create_fact(wrong_result, params)


class TestFactInvariants:
    """Tests for Fact invariants."""

    def test_fact_response_invariant_valid(self):
        """Valid FactResponse passes invariant checks."""
        fact = _make_fact_response()
        assert FactInvariants.fact_response_invariant(fact) is True

    def test_fact_response_invariant_empty_statement(self):
        """FactResponse with empty statement fails invariant."""
        fact = _make_fact_response(statement="")
        with pytest.raises(ValueError, match="statement cannot be empty"):
            FactInvariants.fact_response_invariant(fact)

    def test_canon_level_invariant_all_valid(self):
        """All CanonLevel values are valid for appropriate use."""
        for level in CanonLevel:
            # Just verify they exist and have values
            assert level.value is not None


class TestCanonKeeperExclusivity:
    """Tests for CanonKeeper exclusivity with facts."""

    def test_canon_keeper_write_tool_detection(self):
        """neo4j_create_fact is a CanonKeeper write tool."""
        from monitor_data.invariants.canon_keeper import CanonKeeperExclusivity
        assert CanonKeeperExclusivity.is_canon_keeper_write_tool("neo4j_create_fact") is True

    def test_authorized_writer_canon_keeper(self):
        """CanonKeeper is authorized to create facts."""
        from monitor_data.invariants.canon_keeper import CanonKeeperExclusivity
        assert CanonKeeperExclusivity.is_authorized_writer("neo4j_create_fact", "CanonKeeper") is True

    def test_unauthorized_writer_narrator(self):
        """Narrator is not authorized to create facts."""
        from monitor_data.invariants.canon_keeper import CanonKeeperExclusivity
        assert CanonKeeperExclusivity.is_authorized_writer("neo4j_create_fact", "Narrator") is False

    def test_shared_tool_authorized(self):
        """neo4j_create_source is shared between CanonKeeper and IngestionPipeline."""
        from monitor_data.invariants.canon_keeper import CanonKeeperExclusivity
        assert CanonKeeperExclusivity.is_authorized_writer("neo4j_create_source", "IngestionPipeline") is True

    def test_assert_write_allowed_raises(self):
        """assert_write_allowed raises for unauthorized callers."""
        from monitor_data.invariants.canon_keeper import CanonKeeperExclusivity
        with pytest.raises(PermissionError):
            CanonKeeperExclusivity.assert_write_allowed("neo4j_create_fact", "Narrator")
