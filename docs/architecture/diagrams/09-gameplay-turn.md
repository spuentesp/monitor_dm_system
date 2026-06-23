# 09 — Turno de Juego (Core Narrative Loop)

> Secuencia completa de un turno de juego: desde la acción del jugador hasta
> la canonización, pasando por ContextAssembly, Resolver, Narrator, y CanonKeeper.

## Descripción

Este diagrama muestra el flujo exacto de un turno narrativo en MONITOR.
Es el "core loop" que se ejecuta cada vez que un jugador realiza una acción.

### Nodos del SceneLoop (código real)

El grafo `build_scene_graph()` en `scene_loop.py` define estos nodos:

```
load_context → resolve → narrate → check_events → persist_turn_artifacts → [canonize | END]
```

### Fases del Turno

| Fase | Nodo | Agente | Qué hace |
|------|------|--------|----------|
| S1 | load_context | ContextAssembly | Tri-Modal RAG: Neo4j entities + Qdrant memories + MongoDB turns + game system |
| S3 | resolve | Resolver + GSR | Adjudica acción: parsea tipo, aplica reglas, tira dados, produce outcome + ProposedChanges |
| S4 | narrate | Narrator + DSPy | Genera prosa narrativa inmersiva basada en el outcome |
| — | check_events | ResourceEngine | Fase Alto: detecta spends, aplica earns, dispara thresholds |
| S5 | persist_turn_artifacts | — | Persiste turn + resolution + proposals + checkpoint en MongoDB |
| S6 | canonize | CanonKeeper | (Condicional) Evalúa ProposedChanges y commitea a Neo4j |

### Notas

- `check_events` (ResourceEngine / Fase Alto) se ejecuta entre `narrate` y `persist_turn_artifacts`
- La canonización solo ocurre si `scene_complete` o `turns_count >= max_turns`
- El usuario recibe la respuesta narrativa ANTES de la canonización

## Diagrama

```mermaid
sequenceDiagram
    actor P as 🎮 Jugador
    participant WEB as Web UI (FastAPI)
    participant SL as SceneLoop (LangGraph)
    participant CA as ContextAssembly
    participant N4J as Neo4j
    participant QDR as Qdrant
    participant MONGO as MongoDB
    participant TB as TokenBudget
    participant RES as Resolver
    participant GSR as GameSystemRuntime
    participant NAR as Narrator
    participant RE as ResourceEngine
    participant LLM as LLM Provider
    participant CK as CanonKeeper

    P->>WEB: "Abro el cofre antiguo"
    WEB->>SL: run(user_input, scene_id)

    rect rgb(232, 245, 233)
        Note over SL: Node: load_context (S1)
        SL->>CA: assemble_context(action, scene_id)
        CA->>N4J: get_entities_in_scene(scene_id)
        N4J-->>CA: entities[] (NPCs, locations, objects)
        CA->>N4J: traverse_relationships(entity_ids)
        N4J-->>CA: relationships[] (enemies, allies, located_in)
        CA->>QDR: search_similar(vector_query, top_k=20)
        QDR-->>CA: lore_snippets[], memories[]
        CA->>MONGO: get_recent_turns(scene_id, limit=20)
        MONGO-->>CA: previous_turns[]
        CA->>MONGO: get_game_system(system_id)
        MONGO-->>CA: game_system_schema
        CA->>TB: rank_and_truncate(all_context, max_tokens=2048)
        TB-->>CA: ContextPackage
        CA-->>SL: entities, facts, memories, turns, game_system
    end

    rect rgb(255, 243, 224)
        Note over SL: Node: resolve (S3)
        SL->>RES: resolve_action(action, context)
        RES->>GSR: resolve_check(stat, difficulty, dice_system)
        GSR-->>RES: roll, modifier, total, success
        RES->>LLM: DSPy ResolutionReasoning
        LLM-->>RES: outcome + ProposedChanges
        RES-->>SL: success, outcome, proposed_changes
    end

    rect rgb(227, 242, 253)
        Note over SL: Node: narrate (S4)
        SL->>NAR: narrate_turn(action, resolution, context)
        NAR->>LLM: DSPy NarrativeGeneration + instructor
        LLM-->>NAR: structured prose
        NAR-->>SL: narrative_text + proposals + minutes_elapsed
    end

    rect rgb(224, 247, 250)
        Note over SL: Node: check_events (ResourceEngine)
        SL->>RE: detect_spend(user_input) + apply_earn(resolution) + check_thresholds()
        RE-->>SL: pending_spends[], resource_deltas[], threshold_events[], injected_narrative_events[]
    end

    rect rgb(255, 235, 238)
        Note over SL: Node: persist_turn_artifacts (S5)
        SL->>MONGO: save turn + resolution + proposals + checkpoint
        MONGO-->>SL: turn_id, resolution_id, proposal_ids
    end

    SL-->>WEB: narrative_text, resolution, turn_id
    WEB-->>P: 📖 "El cofre se abre con un crujido..."

    rect rgb(243, 229, 245)
        Note over SL: Node: canonize (S6) — condicional
        SL->>CK: evaluate_proposals(scene_id, proposals)
        CK->>MONGO: get pending proposals
        MONGO-->>CK: ProposedChange[]
        CK->>N4J: check_canon_conflicts(proposals)
        N4J-->>CK: conflicts[]
        CK->>LLM: DSPy evaluation (accept/reject)
        LLM-->>CK: decisions + reasoning
        CK->>N4J: commit_accepted_changes()
        CK->>MONGO: mark_proposals_resolved()
        CK-->>SL: done (clears pending_proposals)
    end
```
