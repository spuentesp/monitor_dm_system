"""
CanonKeeper Exclusivity Invariant (INV-1).

This invariant ensures that ONLY CanonKeeper can write to Neo4j.
This is a CRITICAL invariant for data consistency.

Formal Specification:
    CanonKeeperWrites ==
        ∧ ∀tool ∈ Neo4jWriteTools :
            tool.authorization_check(caller) = CanonKeeper
        ∧ ∀write ∈ Neo4jWriteOps :
            write.initiated_by = CanonKeeper

TLA+ Representation:
    INVARIANT CanonKeeperExclusivity
    -------------------------------------------------
    CanonKeeperExclusivity ==
        ∀node ∈ Neo4jWriteNodes :
            node.lastWriter = "CanonKeeper"
        ∧ ∀edge ∈ CreatedEdges :
            edge.creator = "CanonKeeper"
        ∧ ∀prop ∈ UpdatedProperties :
            prop.editor = "CanonKeeper"
"""

# Tools that ONLY CanonKeeper can call (write operations)
CANON_KEEPER_WRITE_TOOLS: frozenset[str] = frozenset(
    {
        # Universe & Multiverse
        "neo4j_create_multiverse",
        "neo4j_update_multiverse",
        "neo4j_delete_multiverse",
        "neo4j_create_universe",
        "neo4j_update_universe",
        "neo4j_delete_universe",
        "neo4j_ensure_omniverse",
        "neo4j_merge_universes",
        "neo4j_split_universe",
        # Entities
        "neo4j_batch_create_entities",
        "neo4j_batch_update_entities",
        "neo4j_batch_delete_entities",
        "neo4j_create_entity",
        "neo4j_update_entity",
        "neo4j_delete_entity",
        "neo4j_set_state_tags",
        "neo4j_link_to_archetype",
        "neo4j_save_entity_as_template",
        "neo4j_save_template",
        # Relationships
        "neo4j_create_relationship",
        "neo4j_create_character_relationship",
        "neo4j_update_relationship",
        "neo4j_delete_relationship",
        "neo4j_update_state_tags",
        # Facts & Events
        "neo4j_create_fact",
        "neo4j_update_fact",
        "neo4j_delete_fact",
        "neo4j_create_event",
        "neo4j_update_event",
        "neo4j_delete_event",
        "neo4j_create_axiom",
        "neo4j_update_axiom",
        "neo4j_delete_axiom",
        # Stories
        "neo4j_create_story",
        "neo4j_update_story",
        # Mechanics
        "neo4j_create_ability_system",
        "neo4j_create_track",
        "neo4j_create_condition",
        "neo4j_create_resolution_mechanic",
        "neo4j_link_entity_to_ability",
        # Plot Threads
        "neo4j_create_plot_thread",
        "neo4j_update_plot_thread",
        # Parties
        "neo4j_create_party",
        "neo4j_delete_party",
        "neo4j_add_party_member",
        "neo4j_remove_party_member",
        "neo4j_update_party_status",
        "neo4j_update_party_location",
        "neo4j_update_party_formation",
        "neo4j_set_active_pc",
        # Agendas
        "neo4j_create_agenda",
        "neo4j_update_agenda_clock",
        "neo4j_tick_agendas",
    }
)

# Agents that can write to Neo4j (should only be CanonKeeper)
AUTHORIZED_NEO4J_WRITERS: frozenset[str] = frozenset({"CanonKeeper"})

# Tools that CanonKeeper shares with specific agents
SHARED_NEO4J_WRITE_TOOLS: frozenset[str] = frozenset(
    {
        "neo4j_create_source",  # Also IngestionPipeline
        "neo4j_delete_source",  # Also IngestionPipeline
        "neo4j_fork_universe",  # Also WorldArchitect
    }
)

# All Neo4j write tools (including shared)
ALL_NEO4J_WRITE_TOOLS: frozenset[str] = CANON_KEEPER_WRITE_TOOLS | SHARED_NEO4J_WRITE_TOOLS


class CanonKeeperExclusivity:
    """
    Formal invariant checker for CanonKeeper exclusivity.

    This class provides static methods to verify that only CanonKeeper
    (or authorized sharing partners) can perform Neo4j write operations.
    """

    @staticmethod
    def is_canon_keeper_write_tool(tool_name: str) -> bool:
        """
        Check if tool is a CanonKeeper-exclusive write tool.

        Args:
            tool_name: The MCP tool name

        Returns:
            True if tool is CanonKeeper-exclusive
        """
        return tool_name in CANON_KEEPER_WRITE_TOOLS

    @staticmethod
    def is_shared_write_tool(tool_name: str) -> bool:
        """
        Check if tool is a shared Neo4j write tool.

        These tools can be called by both CanonKeeper and specific other agents.

        Args:
            tool_name: The MCP tool name

        Returns:
            True if tool is shared between authorized agents
        """
        return tool_name in SHARED_NEO4J_WRITE_TOOLS

    @staticmethod
    def is_authorized_writer(tool_name: str, agent_type: str) -> bool:
        """
        Check if agent_type is authorized to call tool_name.

        Args:
            tool_name: The MCP tool name
            agent_type: The agent type attempting the call

        Returns:
            True if agent is authorized for this tool
        """
        if tool_name in SHARED_NEO4J_WRITE_TOOLS:
            # Shared tools: CanonKeeper OR IngestionPipeline
            return agent_type in {"CanonKeeper", "IngestionPipeline"}

        if tool_name in CANON_KEEPER_WRITE_TOOLS:
            # Exclusive tools: CanonKeeper only
            return agent_type == "CanonKeeper"

        # Not a write tool - allow read operations
        return True

    @staticmethod
    def get_violation_message(tool_name: str, agent_type: str) -> str:
        """
        Generate detailed violation message for unauthorized access attempt.

        Args:
            tool_name: The MCP tool name
            agent_type: The unauthorized agent type

        Returns:
            Human-readable violation description
        """
        if tool_name in SHARED_NEO4J_WRITE_TOOLS:
            return (
                f"Agent '{agent_type}' is not authorized to call '{tool_name}'. "
                f"Only CanonKeeper and IngestionPipeline can call this tool."
            )

        if tool_name in CANON_KEEPER_WRITE_TOOLS:
            return (
                f"Agent '{agent_type}' is not authorized to call '{tool_name}'. "
                f"Only CanonKeeper can call Neo4j write tools. "
                f"Use ProposedChange in MongoDB instead."
            )

        return f"Unknown tool '{tool_name}'"

    @classmethod
    def assert_write_allowed(cls, tool_name: str, agent_type: str) -> None:
        """
        Assert that agent_type is allowed to call tool_name.

        Raises:
            PermissionError: If agent is not authorized

        Example:
            >>> CanonKeeperExclusivity.assert_write_allowed("neo4j_create_fact", "Narrator")
            PermissionError: Agent 'Narrator' is not authorized to call 'neo4j_create_fact'.
            Only CanonKeeper can call Neo4j write tools.
        """
        if not cls.is_authorized_writer(tool_name, agent_type):
            raise PermissionError(cls.get_violation_message(tool_name, agent_type))


def assert_canon_keeper_only(tool_name: str, agent_type: str) -> None:
    """
    Convenience function to assert CanonKeeper exclusivity.

    This is the primary entry point for enforcement.

    Args:
        tool_name: The MCP tool name
        agent_type: The agent type attempting the call

    Raises:
        PermissionError: If agent is not CanonKeeper (or authorized sharing partner)
    """
    CanonKeeperExclusivity.assert_write_allowed(tool_name, agent_type)


def is_canon_keeper_tool(tool_name: str) -> bool:
    """
    Check if tool is a CanonKeeper-authorized tool.

    Args:
        tool_name: The MCP tool name

    Returns:
        True if tool requires CanonKeeper authority
    """
    return CanonKeeperExclusivity.is_canon_keeper_write_tool(tool_name)


# =============================================================================
# TLA+ SPECIFICATION (for formal verification)
# =============================================================================
r"""
Below is the TLA+ specification for formal verification with TLC model checker.

---------------- MODULE CanonKeeperExclusivity ----------------

EXTENDING Integers, FiniteSets, TLC

CONSTANT
    - Neo4jWriteTools: set of Neo4j write tool names
    - AuthorizedAgents: set of agents allowed to write to Neo4j

VARIABLE
    - call_log: sequence of tool calls (tool_name, agent_type, timestamp)
    - neo4j_state: current Neo4j database state

CanonKeeperExclusivityInvariant ==
    /\ \A call \in call_log:
        LET tool == call.tool_name IN
        LET agent == call.agent_type IN
        /\ tool \in Neo4jWriteTools => agent \in AuthorizedAgents

TypeInvariant ==
    /\ call_log : Seq([tool_name: STRING, agent_type: STRING, timestamp: Int])
    /\ neo4j_state : [last_writer: STRING, nodes: SUBSET STRING, edges: SUBSET STRING]

Init ==
    /\ call_log = <<>>
    /\ neo4j_state = [last_writer |-> "system", nodes |-> {}, edges |-> {}]

Next ==
    \E tool_name \in Neo4jWriteTools:
    \E agent_type \in AuthorizedAgents:
        /\ call_log' = Append(call_log, [tool_name |-> tool_name, agent_type |-> agent_type, timestamp |-> Len(call_log) + 1])
        /\ neo4j_state' = [neo4j_state EXCEPT !.last_writer = agent_type]

THEOREM Invariant => CanonKeeperExclusivityInvariant

=============================================================
"""
