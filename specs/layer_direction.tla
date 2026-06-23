------------------------ MODULE layer_direction ------------------------
(* 
   Layer Direction Invariant (INV-3).
   
   This invariant ensures that dependencies flow in the correct direction:
       Layer 3 (CLI) → Layer 2 (Agents) → Layer 1 (Data Layer)
   
   No layer can import from a layer above it.
   
   Use Cases: SYS-2 (Architecture Enforcement)
*)

EXTENDS Integers, TLC, FiniteSets, Sequences

CONSTANT
    (* Layer numbers - higher = closer to user *)
    EXTERNAL,
    DATA_LAYER,
    AGENTS,
    CLI,
    UI

ASSUME EXTERNAL < DATA_LAYER /\ DATA_LAYER < AGENTS /\ AGENTS < CLI

VARIABLE import_graph

(* Get the layer number for a module *)
GetLayer(module) ==
    IF DOMAIN import_graph /= {} /\ module \in DOMAIN import_graph
    THEN import_graph[module]
    ELSE EXTERNAL

(* Valid import directions:
   - External imports are always valid
   - Same layer imports are always valid
   - Must flow downward (higher number to lower number) *)
ValidImport(source, target) ==
    LET sourceLayer == GetLayer(source)
        targetLayer == GetLayer(target)
    IN
        \/ targetLayer = EXTERNAL
        \/ sourceLayer = targetLayer
        \/ sourceLayer > targetLayer

(* Layer direction invariant: all imports must flow downward *)
LayerDirectionInvariant ==
    \A source \in DOMAIN import_graph :
        \A target \in import_graph[source] :
            ValidImport(source, target)

(* No upward imports *)
NoUpwardImports ==
    \A source \in DOMAIN import_graph :
        \A target \in import_graph[source] :
            GetLayer(source) >= GetLayer(target)

TypeInvariant ==
    import_graph \in [Modules -> SUBSET Modules]

=============================================================================