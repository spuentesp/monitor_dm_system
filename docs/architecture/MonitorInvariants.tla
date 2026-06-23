------------------------------ MODULE MonitorInvariants ------------------------------
(* 
   TLA+ specification for MONITOR critical invariants.
   
   This module formalizes the three most critical invariants that must
   hold across all operations in the MONITOR system.
   
   Run with: tlapm MonitorInvariants.tla
   Or use the VS Code TLA+ extension.
*)

EXTENDS Naturals, Sequences, FiniteSets, TLC

\* =============================================================================
\* CONSTANTS (will be overridden by instantiation)
\* =============================================================================

CONSTANT 
    @ CanonicalAgents,    \* Set of agents that can write canon
    @ Neo4jWriters,       \* Set of agents that can write to Neo4j  
    @ SceneBoundaries    \* Set of scene IDs that define atomic units

\* =============================================================================
\* VARIABLES
\* =============================================================================

VARIABLES
    (\* Neo4j state *)
    neo4j_writes,
    last_writer,
    
    (\* Scene state *)
    scenes,
    scene_facts,
    in_canonization,
    
    (\* ProposedChange workflow *)
    proposed_changes,
    accepted_proposals,
    
    (\* Layer state *)
    layer_imports

\* =============================================================================
\* INITIAL STATE
\* =============================================================================

InitialState == 
    /\ neo4j_writes = <<>>
    /\ last_writer = "None"
    /\ scenes = EmptySet
    /\ scene_facts = [s \in {} |-> <<>>]
    /\ in_canonization = FALSE
    /\ proposed_changes = <<>>
    /\ accepted_proposals = <<>>
    /\ layer_imports = {}   \* No cross-layer imports

\* =============================================================================
\* INVARIANTS
\* =============================================================================

(*
INVARIANT CanonKeeperIs SoleNeo4jWriter
    Only CanonKeeper can initiate writes to Neo4j.
    All other agents must route through ProposedChange workflow.
*)
CanonKeeperIsSoleNeo4jWriter ==
    LET valid_writer(agent) ==
        \/ agent = "CanonKeeper"
        \/ (agent /= "CanonKeeper" /\ Len(neo4j_writes) > 0 
            /\ Head(neo4j_writes).requires_proposed_change)
    IN
    \A write \in neo4j_writes :
        valid_writer(write.agent)

(*
INVARIANT SceneIsAtomicCanonizationUnit
    Facts are canonized as a single atomic unit per scene.
    No partial canonization allowed.
*)
SceneIsAtomicCanonizationUnit ==
    /\ in_canonization = FALSE
        \/ (\E scene \in DOMAIN scene_facts :
            \* All facts for this scene are either all committed or none
            LET scene_committed == scene_facts[scene].committed
            LET all_committed == \A fact \in scene_facts[scene].facts :
                                fact.committed = scene_committed
            IN all_committed)

(*
INVARIANT LayerDependencyDirection
    Dependencies flow downward only:
    - CLI (L3) -> Agents (L2) only
    - Agents (L2) -> Data-Layer (L1) only
    - No skip-layer imports allowed
*)
LayerDependencyDirection ==
    \A import \in layer_imports :
        \/ import.from = "cli" /\ import.to \in {"agents"}
        \/ import.from = "agents" /\ import.to \in {"data-layer"}
        \/ import.from \in {"cli", "agents", "data-layer"} /\ import.to \notin {"cli", "agents", "data-layer"}

(*
INVARIANT ProposedChangeWorkFlow
    All canonical changes go through ProposedChange workflow:
    - Proposed -> Pending review
    - CanonKeeper reviews and accepts/rejects
    - Accepted proposals become canonical
*)
ProposedChangeWorkFlow ==
    \A change \in proposed_changes :
        \/ change.status = "proposed"
        \/ change.status = "pending"
        \/ (change.status = "accepted" /\ change \in accepted_proposals)
        \/ change.status = "rejected"

\* =============================================================================
\* ACTIONS
\* =============================================================================

(\*
Action: Agent writes to Neo4j directly (FORBIDDEN)
*)
AgentDirectNeo4jWrite(agent, tool, params) ==
    /\ agent /= "CanonKeeper"
    /\ neo4j_writes' = Append(neo4j_writes, 
        [agent |-> agent, tool |-> tool, params |-> params, 
         requires_proposed_change |-> TRUE])
    /\ last_writer' = agent
    /\ UNCHANGED <<scenes, scene_facts, in_canonization, 
                    proposed_changes, accepted_proposals, layer_imports>>

(\*
Action: CanonKeeper writes to Neo4j directly (ALLOWED)
*)
CanonKeeperDirectWrite(tool, params) ==
    /\ neo4j_writes' = Append(neo4j_writes,
        [agent |-> "CanonKeeper", tool |-> tool, params |-> params,
         requires_proposed_change |-> FALSE])
    /\ last_writer' = "CanonKeeper"
    /\ UNCHANGED <<scenes, scene_facts, in_canonization,
                    proposed_changes, accepted_proposals, layer_imports>>

(\*
Action: Agent creates ProposedChange (ALLOWED)
*)
AgentCreatesProposedChange(agent, scene_id, content, change_type) ==
    /\ proposed_changes' = Append(proposed_changes,
        [id |-> Len(proposed_changes) + 1,
         agent |-> agent,
         scene_id |-> scene_id,
         content |-> content,
         change_type |-> change_type,
         status |-> "pending",
         evidence |-> <<>>])
    /\ UNCHANGED <<neo4j_writes, last_writer, scenes, scene_facts,
                    in_canonization, accepted_proposals, layer_imports>>

(\*
Action: CanonKeeper accepts proposal and writes to Neo4j (ALLOWED)
*)
CanonKeeperAcceptsAndWrites(proposal_id) ==
    \E proposal \in proposed_changes :
        /\ proposal.status = "pending"
        /\ proposal.id = proposal_id
        /\ accepted_proposals' = Append(accepted_proposals, proposal)
        /\ proposed_changes' = [p \in proposed_changes |-> 
            IF p.id = proposal_id THEN [p EXCEPT !.status = "accepted"]
            ELSE p]
        /\ neo4j_writes' = Append(neo4j_writes,
            [agent |-> "CanonKeeper",
             tool |-> "neo4j_canonize",
             params |-> proposal.content,
             requires_proposed_change |-> FALSE])
        /\ last_writer' = "CanonKeeper"
    /\ UNCHANGED <<scenes, scene_facts, in_canonization, layer_imports>>

(\*
Action: Scene begins canonization (ALLOWED)
*)
BeginSceneCanonization(scene_id) ==
    /\ in_canonization' = TRUE
    /\ scenes' = scenes \cup {scene_id}
    /\ UNCHANGED <<neo4j_writes, last_writer, scene_facts,
                    proposed_changes, accepted_proposals, layer_imports>>

(\*
Action: Scene completes canonization (ALLOWED)
*)
CompleteSceneCanonization(scene_id) ==
    /\ in_canonization' = FALSE
    /\ scene_facts' = [s \in DOMAIN scene_facts |->
        IF s = scene_id
        THEN [scene_facts[s] EXCEPT !.committed = TRUE]
        ELSE scene_facts[s]]
    /\ UNCHANGED <<neo4j_writes, last_writer, scenes,
                    proposed_changes, accepted_proposals, layer_imports>>

(\*
Action: Layer import occurs (check direction)
*)
LayerImportOccurs(from_layer, to_layer) ==
    /\ layer_imports' = layer_imports \cup {[from |-> from_layer, to |-> to_layer]}
    /\ UNCHANGED <<neo4j_writes, last_writer, scenes, scene_facts,
                    in_canonization, proposed_changes, accepted_proposals>>

\* =============================================================================
\* NEXT-STATE RELATION
\* =============================================================================

Next ==
    \E agent \in {"Narrator", "Resolver", "ContextAssembly", "CanonKeeper"} :
    \E tool \in {"neo4j_create_fact", "neo4j_create_entity", "neo4j_create_relationship"} :
    \E params \in {} :
        \/ AgentDirectNeo4jWrite(agent, tool, params)
        \/ CanonKeeperDirectWrite(tool, params)
        \/ AgentCreatesProposedChange(agent, "scene-1", "content", "fact")
        \/ CanonKeeperAcceptsAndWrites(1)
        \/ BeginSceneCanonization("scene-1")
        \/ CompleteSceneCanonization("scene-1")
        \/ LayerImportOccurs("cli", "agents")
        \/ LayerImportOccurs("agents", "data-layer")
        \/ LayerImportOccurs("cli", "data-layer")  \* VIOLATION

\* =============================================================================
\* TEMPORAL PROPERTIES
\* =============================================================================

\* Never allow direct Neo4j writes from non-CanonKeeper
TemporalCanonKeeperExclusivity ==
    <>~(\E write \in neo4j_writes :
        write.agent /= "CanonKeeper" /\ write.requires_proposed_change = TRUE)

\* Always eventually complete canonization once started
TemporalSceneCompleteness ==
    (in_canonization = TRUE) ~> (in_canonization = FALSE)

\* =============================================================================
\* SPECIFICATION
\* =============================================================================

Spec == InitialState /\ [][Next]_vars

\* =============================================================================
\* FAIRNESS
\* =============================================================================

FairSpec == 
    /\ Spec
    /\ WF_vars(CanonKeeperAcceptsAndWrites(1))
    /\ WF_vars(CompleteSceneCanonization("scene-1"))

=============================================================================