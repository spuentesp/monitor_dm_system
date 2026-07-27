------------------------ MODULE canon_keeper ------------------------
(* 
   CanonKeeper Exclusivity Invariant (INV-1).
   
   This invariant ensures that ONLY CanonKeeper can write to Neo4j.
   
   Use Cases: DL-1, DL-2, DL-3, DL-13
*)

EXTENDS Integers, TLC, FiniteSets

CONSTANT
    (* All possible agents *)
    AGENTS
    (* Authorized Neo4j writers - should only contain CanonKeeper *)
    AUTHORIZED_WRITERS
    (* Tools that are write operations *)
    WRITE_TOOLS
    (* Tools that are read operations *)
    READ_TOOLS

ASSUME 
    /\ AUTHORIZED_WRITERS = {CanonKeeper}
    /\ WRITE_TOOLS \cap READ_TOOLS = {}

VARIABLE
    (* Map of tool -> authorized agents *)
    toolAuthorization,
    (* Map of Neo4j operations -> their originating agent *)
    neo4jOperations

(* CanonKeeper is the only one authorized for write tools *)
CanonKeeperExclusivity ==
    /\ \A tool \in WRITE_TOOLS :
        toolAuthorization[tool] = CanonKeeper
    /\ \A op \in DOMAIN neo4jOperations :
        neo4jOperations[op].originator = CanonKeeper

(* No write operation can originate from non-CanonKeeper *)
NoUnauthorizedWrites ==
    \A op \in DOMAIN neo4jOperations :
        neo4jOperations[op].originator = CanonKeeper

(* All read operations are allowed for any agent *)
ReadsArePublic ==
    \A tool \in READ_TOOLS :
        \A agent \in AGENTS : toolAuthorization[tool] = agent

TypeInvariant ==
    /\ toolAuthorization \in [WRITE_TOOLS \cup READ_TOOLS -> AGENTS]
    /\ neo4jOperations \in SUBSET [id: UUID, operation: STRING, originator: AGENTS]

=============================================================================