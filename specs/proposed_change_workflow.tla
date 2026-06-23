------------------------ MODULE proposed_change_workflow ------------------------
(* 
   Proposed Change Workflow Invariant (INV-6).
   
   This invariant ensures that changes follow the workflow:
       Proposed → CanonKeeper Review → Neo4j Commit
   
   Use Cases: DL-1, DL-2, DL-3
*)

EXTENDS Integers, TLC, FiniteSets

CONSTANT
    PENDING,
    UNDER_REVIEW,
    APPROVED,
    REJECTED,
    COMMITTED,
    ROLLED_BACK

VARIABLE proposed_changes, canon_keeper_reviews

(* All valid status values *)
StatusValues == {PENDING, UNDER_REVIEW, APPROVED, REJECTED, COMMITTED, ROLLED_BACK}

(* Valid status transitions *)
ValidTransition(from, to) ==
    \/ from = PENDING /\ to \in {UNDER_REVIEW, REJECTED}
    \/ from = UNDER_REVIEW /\ to \in {APPROVED, REJECTED}
    \/ from = APPROVED /\ to \in {COMMITTED, ROLLED_BACK}
    \/ from = REJECTED /\ to = REJECTED  \* Terminal
    \/ from = COMMITTED /\ to = COMMITTED  \* Terminal
    \/ from = ROLLED_BACK /\ to = ROLLED_BACK  \* Terminal

(* Terminal states - no further transitions allowed *)
TerminalStates == {REJECTED, COMMITTED, ROLLED_BACK}

(* States where change is visible in Neo4j *)
Neo4jVisible == {COMMITTED}

(* Proposed change workflow invariant *)
ProposedChangeWorkflow ==
    /\ \A pc \in proposed_changes :
        pc.status \in StatusValues
    /\ \A pc \in proposed_changes :
        pc.status = COMMITTED => 
            \E ck \in canon_keeper_reviews :
                ck.proposed_change_id = pc.id /\ ck.decision = APPROVED
    /\ \A pc \in proposed_changes :
        pc.status \in {PENDING, UNDER_REVIEW, APPROVED} =>
            ~ \E op \in Neo4jOps : op.source = pc.id

(* All-or-nothing: if committed, all related ops come from same source *)
AllOrNothing ==
    \A pc \in proposed_changes :
        IF pc.status = COMMITTED
        THEN \A op \in Neo4jOps : op.source = pc.id
        ELSE TRUE

TypeInvariant ==
    /\ proposed_changes \subseteq [id: UUID, status: StatusValues, created_at: Time]
    /\ canon_keeper_reviews \subseteq [proposed_change_id: UUID, decision: {APPROVED, REJECTED}, reviewer: Agent]

=============================================================================