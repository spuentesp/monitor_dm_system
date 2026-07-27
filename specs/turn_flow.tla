------------------------ MODULE turn_flow ------------------------
(* 
   Turn Flow Invariant (INV-4).
   
   This invariant ensures that Turns always flow in the correct sequence:
       User Input → Resolve → Narrate
   
   Use Cases: P-1, P-2, P-3
*)

EXTENDS Integers, TLC, FiniteSets, Sequences

CONSTANT
    USER_INPUT,
    RESOLVE,
    NARRATE

ASSUME 
    USER_INPUT < RESOLVE 
    /\ RESOLVE < NARRATE

VARIABLE turns

(* Phase ordering *)
PhaseOrder(p) ==
    CASE p = USER_INPUT -> 1
    [] p = RESOLVE -> 2
    [] p = NARRATE -> 3

(* Valid phase transitions *)
ValidTransition(from, to) ==
    \/ from = USER_INPUT /\ to = RESOLVE
    \/ from = RESOLVE /\ to = NARRATE
    \/ from = NARRATE /\ to = USER_INPUT

(* Turn flow invariant: phases follow correct order *)
TurnFlow ==
    /\ \A i \in 1..Len(turns) :
        turns[i].phase \in {USER_INPUT, RESOLVE, NARRATE}
    /\ \A i \in 1..(Len(turns) - 1) :
        ValidTransition(turns[i].phase, turns[i+1].phase)

(* No skipped phases *)
NoSkippedPhases ==
    \A i \in 1..(Len(turns) - 1) :
        PhaseOrder(turns[i].phase) < PhaseOrder(turns[i+1].phase)

(* No backward transitions *)
NoBackward ==
    \A i \in 1..(Len(turns) - 1) :
        PhaseOrder(turns[i].phase) <= PhaseOrder(turns[i+1].phase)

TypeInvariant ==
    turns \in Seq([phase: {USER_INPUT, RESOLVE, NARRATE}, content: STRING])

=============================================================================