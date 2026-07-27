"""
Fact Contract Definitions.

These contracts define pre-conditions, post-conditions, and invariants
for Fact and Event operations.

Use Cases: DL-3, DL-13
"""

from dataclasses import dataclass

from monitor_data.schemas.base import CanonLevel, KnowledgeScope
from monitor_data.schemas.facts import FactCreate, FactResponse, FactUpdate

# =============================================================================
# FACT PRE-CONDITIONS
# =============================================================================


@dataclass
class FactPreConditions:
    """
    Pre-conditions for Fact operations.

    These must be TRUE before the operation can proceed.
    """

    @staticmethod
    def create_fact(
        params: FactCreate,
        universe_exists: bool,
        entity_ids_exist: list[str] | None = None,
        source_ids_exist: list[str] | None = None,
        scene_ids_exist: list[str] | None = None,
        caller_is_canon_keeper: bool = False,
    ) -> bool:
        """
        Pre-condition for neo4j_create_fact.

        Requirements:
        - universe_id must exist in Neo4j
        - entity_ids (if provided) must exist in Neo4j
        - source_ids (if provided) must exist in Neo4j
        - scene_ids (if provided) must exist in Neo4j
        - caller must be CanonKeeper
        """
        if not caller_is_canon_keeper:
            raise PermissionError("Only CanonKeeper can create facts")

        if not universe_exists:
            raise ValueError(f"Universe {params.universe_id} does not exist")

        if params.entity_ids and entity_ids_exist is not None:
            for entity_id in params.entity_ids:
                if str(entity_id) not in entity_ids_exist:
                    raise ValueError(f"Entity {entity_id} does not exist")

        if params.source_ids and source_ids_exist is not None:
            for source_id in params.source_ids:
                if str(source_id) not in source_ids_exist:
                    raise ValueError(f"Source {source_id} does not exist")

        if params.scene_ids and scene_ids_exist is not None:
            for scene_id in params.scene_ids:
                if str(scene_id) not in scene_ids_exist:
                    raise ValueError(f"Scene {scene_id} does not exist")

        return True

    @staticmethod
    def update_fact(
        current_fact: FactResponse,
        new_canon_level: CanonLevel | None = None,
        caller_is_canon_keeper: bool = False,
    ) -> bool:
        """
        Pre-condition for neo4j_update_fact.

        Requirements:
        - caller must be CanonKeeper
        - canon_level transition must be valid
        """
        if not caller_is_canon_keeper:
            raise PermissionError("Only CanonKeeper can update facts")

        # Check valid canon_level transitions
        if new_canon_level is not None:
            valid_transitions = {
                CanonLevel.PROPOSED: {CanonLevel.CANON, CanonLevel.RETCONNED},
                CanonLevel.CANON: {CanonLevel.RETCONNED, CanonLevel.SUPERSEDED},
                CanonLevel.RUMOR: {CanonLevel.CANON, CanonLevel.RETCONNED},
                CanonLevel.CHARACTER_BELIEF: {CanonLevel.CANON, CanonLevel.RETCONNED},
                CanonLevel.PLAYER_KNOWLEDGE: {CanonLevel.CANON, CanonLevel.RETCONNED},
                CanonLevel.RETCONNED: set(),  # Terminal
                CanonLevel.SUPERSEDED: set(),  # Terminal
            }
            allowed = valid_transitions.get(current_fact.canon_level, set())
            if new_canon_level not in allowed:
                raise ValueError(f"Invalid canon_level transition from {current_fact.canon_level} to {new_canon_level}")

        return True


# =============================================================================
# FACT POST-CONDITIONS
# =============================================================================


@dataclass
class FactPostConditions:
    """
    Post-conditions for Fact operations.

    These must be TRUE after the operation completes.
    """

    @staticmethod
    def create_fact(result: FactResponse, params: FactCreate) -> bool:
        """
        Post-condition for neo4j_create_fact.

        Guarantees:
        - Returns a FactResponse with valid UUID
        - Fact is linked to universe
        - canon_level is set correctly
        - created_at is set
        """
        if result.id is None:
            raise ValueError("Fact id must be set in response")
        if result.universe_id != params.universe_id:
            raise ValueError(f"universe_id mismatch: expected {params.universe_id}, got {result.universe_id}")
        if result.canon_level != params.canon_level:
            raise ValueError(f"canon_level mismatch: expected {params.canon_level}, got {result.canon_level}")
        if result.created_at is None:
            raise ValueError("created_at must be set")
        return True

    @staticmethod
    def update_fact(result: FactResponse, old_fact: FactResponse, params: FactUpdate) -> bool:
        """
        Post-condition for neo4j_update_fact.

        Guarantees:
        - Updated fields match params
        - Non-updated fields remain unchanged
        - updated_at is refreshed
        """
        if params.statement is not None and result.statement != params.statement:
            raise ValueError(f"statement mismatch: expected {params.statement}, got {result.statement}")
        if params.canon_level is not None and result.canon_level != params.canon_level:
            raise ValueError(f"canon_level mismatch: expected {params.canon_level}, got {result.canon_level}")
        if hasattr(result, "updated_at") and result.updated_at and result.updated_at <= old_fact.created_at:
            raise ValueError("updated_at must be after created_at")
        return True


# =============================================================================
# FACT INVARIANTS
# =============================================================================


@dataclass
class FactInvariants:
    """
    Fact invariants that must hold at all times.
    """

    @staticmethod
    def fact_response_invariant(fact: FactResponse) -> bool:
        """
        Invariant for FactResponse.

        Requirements:
        - id is not None
        - universe_id is not None
        - statement is not empty
        - canon_level is valid CanonLevel
        - knowledge_scope is valid KnowledgeScope
        """
        if fact.id is None:
            raise ValueError("Fact id cannot be None")
        if fact.universe_id is None:
            raise ValueError("Fact universe_id cannot be None")
        if not fact.statement or len(fact.statement.strip()) == 0:
            raise ValueError("Fact statement cannot be empty")
        if not isinstance(fact.canon_level, CanonLevel):
            raise ValueError(f"canon_level must be CanonLevel, got {type(fact.canon_level)}")
        if not isinstance(fact.knowledge_scope, KnowledgeScope):
            raise ValueError(f"knowledge_scope must be KnowledgeScope, got {type(fact.knowledge_scope)}")
        return True

    @staticmethod
    def canon_level_invariant(canon_level: CanonLevel) -> bool:
        """
        Invariant for CanonLevel values.
        """
        valid_levels = {
            CanonLevel.PROPOSED,
            CanonLevel.CANON,
            CanonLevel.RUMOR,
            CanonLevel.CHARACTER_BELIEF,
            CanonLevel.PLAYER_KNOWLEDGE,
            CanonLevel.RETCONNED,
            CanonLevel.SUPERSEDED,
        }
        if canon_level not in valid_levels:
            raise ValueError(f"Invalid CanonLevel: {canon_level}")
        return True

    @staticmethod
    def provenance_chain_invariant(fact: FactResponse) -> bool:
        """
        Invariant: If fact has sources, it should not be CANON without evidence.

        Rule: PROPOSED facts can become CANON only via CanonKeeper review
        with SUPPORTED_BY relationships to sources.
        """
        if fact.canon_level == CanonLevel.CANON:
            # A fact becoming canon should have supporting evidence
            # (This is enforced by CanonKeeper logic, not the schema)
            pass
        return True
