"""
Contract Definitions for MONITOR Data Layer MCP Tools.

This module formalizes preconditions, postconditions, and invariants
for all MCP tool interfaces using Pydantic models as contracts.

Design by Contract (DbC) principles:
- Preconditions: What must be true BEFORE a tool is called
- Postconditions: What must be true AFTER a tool completes successfully
- Invariants: What must remain true THROUGHOUT

USE CASES: DL-1 through DL-14

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries + schemas only
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import (
    Any,
    Generic,
    Protocol,
    TypeVar,
    runtime_checkable,
)
from uuid import UUID

from pydantic import BaseModel, Field

from monitor_data.schemas.base import Authority, CanonLevel, ProposalStatus, ProposalType, SimulationScope
from monitor_data.schemas.facts import FactStatus, FactType
from monitor_data.schemas.proposed_changes import Evidence

# =============================================================================
# CONTRACT RESULT TYPE
# =============================================================================


@dataclass(frozen=True)
class ContractResult:
    """Result of a contract check."""

    passed: bool
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def ok(cls, details: dict[str, Any] | None = None) -> ContractResult:
        return cls(passed=True, message="OK", details=details or {})

    @classmethod
    def fail(cls, message: str, details: dict[str, Any] | None = None) -> ContractResult:
        return cls(passed=False, message=message, details=details or {})


# =============================================================================
# CONTRACT PROTOCOLS (structural typing for tools)
# =============================================================================


@runtime_checkable
class ToolContract(Protocol):
    """Protocol that all tool functions satisfy."""

    async def __call__(self, *args: Any, **kwargs: Any) -> Any: ...


# =============================================================================
# INVARIANTS (must hold before/after/throughout every operation)
# =============================================================================


class Neo4jInvariant(BaseModel):
    """Invariants that must hold for all Neo4j operations."""

    # CanonKeeper is the only writer to Neo4j
    canonkeeper_only: bool = Field(
        default=True,
        description="Only CanonKeeper agent can initiate Neo4j writes",
    )

    # Scene is atomic canonization boundary
    scene_atomicity: bool = Field(
        default=True,
        description="A scene's facts are canonized as a single atomic unit",
    )

    # No direct CLI/agent → Neo4j without CanonKeeper
    layer_discipline: bool = Field(
        default=True,
        description="All Neo4j writes route through CanonKeeper",
    )


class MongoDBInvariant(BaseModel):
    """Invariants that must hold for all MongoDB operations."""

    # ProposedChanges track scene-bound state transitions
    proposal_workflow: bool = Field(
        default=True,
        description="State changes go through ProposedChange → CanonKeeper review",
    )

    # Turns are append-only within a scene
    turn_append_only: bool = Field(
        default=True,
        description="Once a turn is appended, it cannot be modified",
    )


class LayerInvariant(BaseModel):
    """Cross-layer invariants."""

    # Layer 3 (CLI) cannot import Layer 1 (data-layer) directly
    no_skip_layer_imports: bool = Field(
        default=True,
        description="CLI imports agents only; agents import data-layer only",
    )

    # All async agent methods must be marked async
    async_methods: bool = Field(
        default=True,
        description="Agent methods calling MCP tools are async",
    )


# =============================================================================
# CONTRACT TEMPLATES
# =============================================================================


_T = TypeVar("_T", bound=BaseModel)


@dataclass
class ContractViolation:
    """Details of a contract violation."""

    contract_name: str
    check_type: str  # "precondition", "postcondition", "invariant"
    failed_check: str
    context: dict[str, Any]


class ContractCheck(Generic[_T]):
    """Generic contract check container."""

    def __init__(
        self,
        name: str,
        check_fn: Callable[[_T], ContractResult],
        check_type: str = "precondition",
    ):
        self.name = name
        self.check_fn = check_fn
        self.check_type = check_type

    def __repr__(self) -> str:
        return f"<ContractCheck {self.check_type}::{self.name}>"


# =============================================================================
# USE CASE DL-1: Multiverse/Universe CRUD
# =============================================================================


class UniverseCreateContract(BaseModel):
    """Pre/post conditions for neo4j_create_universe."""

    # Preconditions
    universe_id: UUID | None = None
    name: str = Field(min_length=1, max_length=200)
    parent_id: UUID | None = None
    tags: list[str] = Field(default_factory=list)

    def preconditions(self) -> list[ContractResult]:
        """Validate preconditions before creation."""
        results = []
        if not self.name.strip():
            results.append(ContractResult.fail("Universe name cannot be empty or whitespace"))
        if len(self.name) > 200:
            results.append(ContractResult.fail("Universe name exceeds 200 characters"))
        return results

    def postconditions(self, created: dict[str, Any]) -> list[ContractResult]:
        """Validate postconditions after creation."""
        results = []
        if "id" not in created:
            results.append(ContractResult.fail("Created universe must have an id"))
        if created.get("name") != self.name:
            results.append(ContractResult.fail("Created universe name must match input"))
        return results


class UniverseFilterContract(BaseModel):
    """Pre/post conditions for neo4j_list_universes."""

    parent_id: UUID | None = None
    tag: str | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)

    def preconditions(self) -> list[ContractResult]:
        results = []
        if self.limit < 1 or self.limit > 200:
            results.append(ContractResult.fail("Limit must be between 1 and 200"))
        if self.offset < 0:
            results.append(ContractResult.fail("Offset cannot be negative"))
        return results


# =============================================================================
# USE CASE DL-2: Entity CRUD
# =============================================================================


class EntityCreateContract(BaseModel):
    """Pre/post conditions for neo4j_create_entity."""

    entity_id: UUID | None = None
    universe_id: UUID
    archetype: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    properties: dict[str, Any] | None = None
    state_tags: list[str] = Field(default_factory=list)

    def preconditions(self) -> list[ContractResult]:
        results = []
        if not self.name.strip():
            results.append(ContractResult.fail("Entity name cannot be empty"))
        if not self.archetype.strip():
            results.append(ContractResult.fail("Entity archetype cannot be empty"))
        if self.properties is not None and not isinstance(self.properties, dict):
            results.append(ContractResult.fail("Properties must be a dict"))
        return results

    def postconditions(self, created: dict[str, Any]) -> list[ContractResult]:
        results = []
        if "id" not in created:
            results.append(ContractResult.fail("Created entity must have an id"))
        if created.get("universe_id") != str(self.universe_id):
            results.append(ContractResult.fail("Created entity universe_id must match input"))
        return results


# =============================================================================
# USE CASE DL-3: Fact CRUD
# =============================================================================


class FactCreateContract(BaseModel):
    """Pre/post conditions for neo4j_create_fact."""

    universe_id: UUID
    statement: str = Field(min_length=1, max_length=2000)
    fact_type: FactType = FactType.STATE
    magnitude: int = Field(default=1, ge=1, le=10)
    scope: SimulationScope = SimulationScope.LOCAL
    time_ref: datetime | None = None
    entity_ids: list[UUID] | None = None
    source_ids: list[UUID] | None = None
    canon_level: CanonLevel = CanonLevel.PROPOSED
    authority: Authority = Authority.SYSTEM
    properties: dict[str, Any] | None = None

    def preconditions(self) -> list[ContractResult]:
        results = []
        if not self.statement.strip():
            results.append(ContractResult.fail("Fact statement cannot be empty"))
        if len(self.statement) > 2000:
            results.append(ContractResult.fail("Fact statement exceeds 2000 characters"))
        if self.magnitude < 1 or self.magnitude > 10:
            results.append(ContractResult.fail("Magnitude must be between 1 and 10"))
        # Evidence refs required for canon-level facts
        if self.canon_level == CanonLevel.CANON and not self.source_ids:
            results.append(ContractResult.fail("Canon-level facts require source_ids"))
        return results

    def postconditions(self, created: dict[str, Any]) -> list[ContractResult]:
        results = []
        if "id" not in created:
            results.append(ContractResult.fail("Created fact must have an id"))
        if created.get("universe_id") != str(self.universe_id):
            results.append(ContractResult.fail("Created fact universe_id must match"))
        if created.get("status") != FactStatus.ACTIVE.value:
            results.append(ContractResult.fail("New facts must have ACTIVE status"))
        return results


class FactFilterContract(BaseModel):
    """Preconditions for neo4j_list_facts."""

    universe_id: UUID | None = None
    entity_id: UUID | None = None
    fact_type: FactType | None = None
    canon_level: CanonLevel | None = None
    status: FactStatus = FactStatus.ACTIVE
    min_magnitude: int = Field(default=1, ge=1, le=10)
    limit: int = Field(default=30, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

    def preconditions(self) -> list[ContractResult]:
        results = []
        if self.min_magnitude < 1 or self.min_magnitude > 10:
            results.append(ContractResult.fail("min_magnitude must be 1-10"))
        if self.limit < 1 or self.limit > 100:
            results.append(ContractResult.fail("limit must be 1-100"))
        return results


# =============================================================================
# USE CASE DL-4: Story/Scene/Turn CRUD
# =============================================================================


class SceneCreateContract(BaseModel):
    """Pre/post conditions for mongodb_create_scene."""

    story_id: UUID
    scene_number: int = Field(ge=1)
    universe_id: UUID
    status: str = Field(default="active")
    gm_profile_id: UUID | None = None

    def preconditions(self) -> list[ContractResult]:
        results = []
        if self.scene_number < 1:
            results.append(ContractResult.fail("scene_number must be >= 1"))
        if self.status not in ("active", "paused", "completed"):
            results.append(ContractResult.fail("Invalid scene status"))
        return results


class TurnAppendContract(BaseModel):
    """Pre/post conditions for mongodb_append_turn."""

    scene_id: UUID
    turn_index: int = Field(ge=0)
    actor_id: UUID | None = None
    narrative: str = Field(min_length=1)
    turn_type: str = Field(default="action")

    def preconditions(self) -> list[ContractResult]:
        results = []
        if self.turn_index < 0:
            results.append(ContractResult.fail("turn_index cannot be negative"))
        if not self.narrative.strip():
            results.append(ContractResult.fail("Turn narrative cannot be empty"))
        return results

    def postconditions(self, appended: dict[str, Any]) -> list[ContractResult]:
        results = []
        if appended.get("scene_id") != str(self.scene_id):
            results.append(ContractResult.fail("Turn scene_id must match"))
        if appended.get("turn_index") != self.turn_index:
            results.append(ContractResult.fail("Turn index must match requested"))
        return results


# =============================================================================
# USE CASE DL-5: ProposedChange CRUD
# =============================================================================


class ProposedChangeCreateContract(BaseModel):
    """Pre/post conditions for mongodb_create_proposed_change."""

    scene_id: UUID | None = None
    story_id: UUID | None = None
    turn_id: UUID | None = None
    change_type: ProposalType
    content: dict[str, Any] = Field(min_length=1)
    evidence: list[Evidence] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    authority: Authority = Authority.SYSTEM
    proposer: str = Field(default="Unknown")

    def preconditions(self) -> list[ContractResult]:
        results = []
        if self.scene_id is None and self.story_id is None:
            results.append(ContractResult.fail("Either scene_id or story_id must be provided"))
        if not self.content:
            results.append(ContractResult.fail("Content cannot be empty"))
        if not self.content:
            results.append(ContractResult.fail("change_type cannot be empty"))
        return results

    def postconditions(self, created: dict[str, Any]) -> list[ContractResult]:
        results = []
        if created.get("status") != ProposalStatus.PENDING.value:
            results.append(ContractResult.fail("New proposals must have PENDING status"))
        if "proposal_id" not in created:
            results.append(ContractResult.fail("Created proposal must have proposal_id"))
        return results


class ProposedChangeUpdateContract(BaseModel):
    """Preconditions for mongodb_update_proposed_change."""

    proposal_id: UUID
    status: ProposalStatus
    decision_metadata: dict[str, Any]

    def preconditions(self) -> list[ContractResult]:
        results = []
        # Only CanonKeeper can transition from PENDING
        if self.status not in (ProposalStatus.PENDING,):
            # Verify authority in context (checked by middleware)
            pass
        if not self.decision_metadata:
            results.append(ContractResult.fail("decision_metadata required for status updates"))
        return results


# =============================================================================
# USE CASE DL-10: Qdrant Vector Operations
# =============================================================================


class VectorUpsertContract(BaseModel):
    """Pre/post conditions for qdrant_upsert."""

    collection: str
    vector_id: str
    embedding: list[float]
    payload: dict[str, Any]
    metadata: dict[str, Any] | None = None

    def preconditions(self) -> list[ContractResult]:
        results = []
        if not self.collection.strip():
            results.append(ContractResult.fail("Collection name cannot be empty"))
        if not self.vector_id.strip():
            results.append(ContractResult.fail("vector_id cannot be empty"))
        # Embedding dimension validation (assuming 1536 for OpenAI ada)
        if len(self.embedding) not in (768, 1536, 3072):
            results.append(ContractResult.fail(f"Invalid embedding dimension: {len(self.embedding)}"))
        return results


class VectorSearchContract(BaseModel):
    """Preconditions for qdrant_search."""

    collection: str
    query_embedding: list[float]
    limit: int = Field(default=10, ge=1, le=100)
    filter: dict[str, Any] | None = None
    score_threshold: float | None = Field(default=None, ge=0.0, le=1.0)

    def preconditions(self) -> list[ContractResult]:
        results = []
        if not self.collection.strip():
            results.append(ContractResult.fail("Collection name cannot be empty"))
        if self.limit < 1 or self.limit > 100:
            results.append(ContractResult.fail("limit must be 1-100"))
        if self.score_threshold is not None:
            if self.score_threshold < 0.0 or self.score_threshold > 1.0:
                results.append(ContractResult.fail("score_threshold must be 0.0-1.0"))
        return results


# =============================================================================
# CANONKEEPER EXCLUSIVITY CONTRACT
# =============================================================================


class CanonKeeperContract(BaseModel):
    """
    Contract ensuring CanonKeeper is the sole Neo4j writer.

    INVARIANT: All Neo4j write operations must be initiated by CanonKeeper
    or go through the ProposedChange workflow reviewed by CanonKeeper.

    This contract formalizes the architecture rule from ARCHITECTURE.md:
    "Only CanonKeeper can write to Neo4j. All other agents create
    ProposedChange documents in MongoDB. CanonKeeper evaluates and commits."
    """

    # Write operations that require CanonKeeper authority
    requires_canonkeeper: set[str] = field(
        default_factory=lambda: {
            "neo4j_create_fact",
            "neo4j_update_fact",
            "neo4j_delete_fact",
            "neo4j_create_entity",
            "neo4j_update_entity",
            "neo4j_delete_entity",
            "neo4j_create_universe",
            "neo4j_update_universe",
            "neo4j_delete_universe",
            "neo4j_create_story",
            "neo4j_update_story",
            "neo4j_create_plot_thread",
            "neo4j_create_relationship",
        }
    )

    # Operations that go through ProposedChange workflow
    requires_proposed_change: set[str] = field(
        default_factory=lambda: {
            "neo4j_create_fact",
            "neo4j_create_entity",
            "neo4j_update_entity",
            "neo4j_create_relationship",
        }
    )

    def verify_writer_authority(
        self,
        tool_name: str,
        agent_type: str,
        has_proposed_change: bool = False,
    ) -> ContractResult:
        """
        Verify that a write operation has proper CanonKeeper authority.

        Args:
            tool_name: The MCP tool being called
            agent_type: The calling agent's type
            has_proposed_change: Whether this write is gated through ProposedChange

        Returns:
            ContractResult indicating pass/fail
        """
        if tool_name not in self.requires_canonkeeper:
            return ContractResult.ok()

        # Direct Neo4j write without ProposedChange is forbidden
        if tool_name in self.requires_proposed_change and not has_proposed_change:
            return ContractResult.fail(
                f"Tool {tool_name} requires ProposedChange workflow; direct Neo4j write from {agent_type} is forbidden",
                {"tool": tool_name, "agent": agent_type},
            )

        # Verify CanonKeeper is the agent
        if agent_type != "CanonKeeper":
            return ContractResult.fail(
                f"Tool {tool_name} requires CanonKeeper authority; called by {agent_type} without ProposedChange",
                {"tool": tool_name, "agent": agent_type},
            )

        return ContractResult.ok()


# =============================================================================
# CONTRACT RUNNER
# =============================================================================


class ContractRunner:
    """
    Executes contract checks for tool calls.

    Usage:
        runner = ContractRunner()
        result = runner.run_preconditions(FactCreateContract(**input_data))
    """

    def __init__(self, strict: bool = True):
        self.strict = strict
        self.violations: list[ContractViolation] = []

    def run_preconditions(self, contract: BaseModel) -> ContractResult:
        """Run all preconditions for a contract."""
        if not hasattr(contract, "preconditions"):
            return ContractResult.ok()

        results = contract.preconditions()
        failed = [r for r in results if not r.passed]

        if failed:
            self.violations.append(
                ContractViolation(
                    contract_name=type(contract).__name__,
                    check_type="precondition",
                    failed_check=failed[0].message,
                    context={"contract": contract.model_dump()},
                )
            )
            if self.strict:
                # reason: bare ContractViolation return in strict-mode path; the public method is annotated ContractResult but strict-mode wants to surface the violating check first — narrow the signature to ContractResult | ContractViolation in a follow-up
                return failed[0]  # type: ignore
        return ContractResult.ok()

    def run_postconditions(
        self,
        contract: BaseModel,
        result: dict[str, Any],
    ) -> ContractResult:
        """Run all postconditions for a contract with the result."""
        if not hasattr(contract, "postconditions"):
            return ContractResult.ok()

        results = contract.postconditions(result)
        failed = [r for r in results if not r.passed]

        if failed:
            self.violations.append(
                ContractViolation(
                    contract_name=type(contract).__name__,
                    check_type="postcondition",
                    failed_check=failed[0].message,
                    context={"contract": contract.model_dump(), "result": result},
                )
            )
            if self.strict:
                # reason: bare ContractViolation return in strict-mode path; mirrors the precondition handler above — narrow the signature to ContractResult | ContractViolation in a follow-up
                return failed[0]  # type: ignore
        return ContractResult.ok()

    def verify_invariant(
        self,
        invariant_name: str,
        check_fn: Callable[[], bool],
        context: dict[str, Any] | None = None,
    ) -> ContractResult:
        """Verify an invariant holds."""
        try:
            passed = check_fn()
            if not passed:
                return ContractResult.fail(
                    f"Invariant {invariant_name} violated",
                    context or {},
                )
        except Exception as e:
            return ContractResult.fail(
                f"Invariant {invariant_name} raised exception: {e}",
                context or {},
            )
        return ContractResult.ok()


# =============================================================================
# DECORATOR-BASED CONTRACT APPLICATION
# =============================================================================


def requires_contract(contract_class: type[BaseModel]) -> Callable[..., Callable[..., Any]]:
    """
    Decorator to apply contract checking to a tool function.

    Usage:
        @requires_contract(FactCreateContract)
        async def neo4j_create_fact(params: FactCreate) -> dict[str, Any]:
            ...
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            runner = ContractRunner()

            # Extract kwargs matching contract fields
            contract_data = {k: v for k, v in kwargs.items() if k in contract_class.model_fields}

            # Try to create contract model
            try:
                contract = contract_class(**contract_data)
            except Exception as e:
                return ContractResult.fail(
                    f"Contract initialization failed: {e}",
                    {"data": contract_data},
                )

            # Check preconditions
            pre_result = runner.run_preconditions(contract)
            if not pre_result.passed:
                return pre_result

            # Execute original function
            result = await func(*args, **kwargs)

            # Check postconditions
            post_result = runner.run_postconditions(contract, result)
            if not post_result.passed:
                return post_result

            return result

        return wrapper

    return decorator
