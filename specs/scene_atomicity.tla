------------------------ MODULE scene_atomicity ------------------------
(* 
   Scene Atomicity Invariant (INV-2).
   
   This invariant ensures that Scene is the atomic canonization boundary.
   All facts within a scene must be canonized together or not at all.
   
   Use Cases: DL-4, P-1, P-2, P-3, P-8
*)

EXTENDS Integers, TLC, FiniteSets

CONSTANT 
    (* Status values that scenes can have *)
    ACTIVE,
    FINALIZING, 
    COMPLETED

ASSUME 
    /\ ACTIVE # FINALIZING
    /\ FINALIZING # COMPLETED
    /\ ACTIVE # COMPLETED

VARIABLE scenes, proposed_changes

(* Valid status transitions *)
ValidTransitions == 
    /\ ACTIVE :> {FINALIZING, COMPLETED}
    /\ FINALIZING :> {ACTIVE, COMPLETED}
    /\ COMPLETED :> {}

(* Terminal states - no further transitions allowed *)
TerminalStates == {COMPLETED}

(* States that indicate scene is in progress *)
InProgressStates == {ACTIVE, FINALIZING}

(* Scene atomicity: all proposed changes within a scene are all-or-nothing *)
SceneAtomicity ==
    /\ \A s \in scenes :
        s.status = COMPLETED <=> 
            \A pc \in proposed_changes : 
                pc.scene_id = s.id => pc.status = "committed"

AllOrNothing ==
    \A s \in scenes :
        IF s.status = COMPLETED
        THEN \A pc \in proposed_changes : 
            pc.scene_id = s.id => pc.status = "committed"
        ELSE \A pc \in proposed_changes : 
            pc.scene_id = s.id => pc.status # "committed"

TypeInvariant ==
    /\ scenes \subseteq [id: UUID, status: {ACTIVE, FINALIZING, COMPLETED}]
    /\ proposed_changes \subseteq [id: UUID, scene_id: UUID, status: {"pending", "committed", "rolled_back"}]

=============================================================================