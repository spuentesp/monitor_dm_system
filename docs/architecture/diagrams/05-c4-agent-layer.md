# 05 — C4 Componentes: Agent Layer (Nivel 3)

> Componentes internos del Agent Layer (`monitor-agents`).
> LangGraph Loops, Specialized Agents, y AI/Prompt Modules.

## Descripción

El Agent Layer contiene 6 StateGraphs de LangGraph, 12 agentes especializados,
y 3 módulos de IA. Todo es stateless — el estado se persiste en MongoDB vía MongoDBSaver.

### Loops (StateGraphs)

| Loop | Archivo | Estado | Nodos |
|------|---------|--------|-------|
| StoryLoop | `story_loop.py` | StoryState | init_story, run_scene, evaluate_arc, world_advance, transition, finalize |
| SceneLoop | `scene_loop.py` | SceneState | load_context, resolve, narrate, check_events, persist_turn_artifacts, canonize |
| CombatLoop | `combat_loop.py` | CombatState | roll_initiative, choose_combatant, resolve_action, narrate_combat, check_victory |
| ConversationLoop | `conversation_loop.py` | ConversationState | open_session, load_npc_context, process_player_turn, generate_npc_responses, close_session |
| WorldBuildingLoop | `world_building_loop.py` | WorldBuildingState | load_world_context, process_user_input, commit_proposals, format_response |
| CharacterCreationLoop | `character_creation_loop.py` | CharacterCreationState | load_system, present_step, await_player, process_input |

### Agentes

| Agente | Archivo | Rol | Escritura |
|--------|---------|-----|-----------|
| ContextAssembly | `context_assembly.py` | Tri-Modal RAG (Neo4j+Qdrant+MongoDB) | Read-Only |
| Resolver | `resolver.py` | Adjudica reglas y dados | MongoDB (Resolutions) |
| Narrator | `narrator.py` | Genera prosa narrativa (DSPy+instructor) | MongoDB (Turns) |
| CanonKeeper | `canonkeeper.py` | Guardián de verdad | **Neo4j (Exclusive)** |
| Indexer | `indexer.py` | Chunking + embedding | Qdrant |
| Analyzer | `analyzer.py` | Extracción DSPy multi-query | MongoDB (KnowledgePacks) |
| IngestionPipeline | `ingestion_pipeline.py` | Orquesta Indexer + Analyzer | MinIO, Neo4j (Source), MongoDB |
| WorldArchitect | `world_architect.py` | Construcción colaborativa | Neo4j (vía CanonKeeper) |
| NPCVoice | `npc_voice.py` | Habla como NPC específico | MongoDB (Turns) |
| RecapAgent | `recap_agent.py` | Sintetiza historia | Read-Only |
| SimulacrumAgent | `simulacrum.py` | Simula facciones y NPCs off-screen | MongoDB (Proposals) |
| NPCSceneGenerator | `npc_scene_generator.py` | Genera escenas procedurales | MongoDB (Scenes) |

### AI Modules

| Módulo | Archivo | Rol |
|--------|---------|-----|
| DSPy Modules | `prompts/` | QueryFormulation, KnowledgeExtraction, NarrativeGeneration, ResolutionReasoning |
| GameSystemRuntime | `game_system.py` | Resolución de stats, dados + modificadores, creación de personaje |
| TokenBudget | `token_budget.py` | Ranking + truncación de contexto, priorización de items |

### Composición Interna

- `IngestionPipeline` compone `Indexer` + `Analyzer` internamente (atributos `self._indexer`, `self._analyzer`)
- `Narrator` usa `AgentToolAdapter` internamente para adaptar llamadas MCP

## Diagrama

```mermaid
graph TB
    subgraph L2["📦 monitor-agents"]
        subgraph LOOPS["LangGraph StateGraph Loops"]
            STORY["StoryLoop\nstory_loop.py\nState: StoryState\ninit_story → run_scene → evaluate_arc\n→ transition / finalize\nWorld Advance via Simulacrum"]
            SCENE["SceneLoop\nscene_loop.py\nState: SceneState\nload_context → resolve → narrate\n→ check_events → persist_turn_artifacts\n→ canonize / END\nMongoDBSaver checkpointing"]
            COMBAT["CombatLoop\ncombat_loop.py\nState: CombatState\ninitiative → choose → resolve\n→ narrate → check_victory\nEmbebido en SceneLoop"]
            CONV["ConversationLoop\nconversation_loop.py\nState: ConversationState\nopen_session → load_npc_context\n→ process_player_turn → generate_npc_responses\n→ close_session\nModos: DIRECT y ACTOR"]
            WORLD["WorldBuildingLoop\nworld_building_loop.py\nState: WorldBuildingState\nload_world_context → process_user_input\n→ commit_proposals → format_response\nAuto-commitea propuestas"]
            CHAR["CharacterCreationLoop\ncharacter_creation_loop.py\nState: CharacterCreationState\nload_system → present_step\n→ await_player → process_input\nSchema-driven (GSR)"]
        end

        subgraph AGENTS["Specialized Agents (BaseAgent)"]
            CA["ContextAssembly\ncontext_assembly.py\nTri-Modal RAG:\n· Neo4j (structural)\n· Qdrant (semantic)\n· MongoDB (narrative)\n→ Context Package"]
            RES["Resolver\nresolver.py\nAdjudica reglas y dados\nUsa GameSystemRuntime\n→ Outcome + ProposedChanges"]
            NAR["Narrator\nnarrator.py\nGenera prosa narrativa\nUsa DSPy + instructor\nUsa AgentToolAdapter\n→ Immersive prose + Turn"]
            CK["CanonKeeper\ncanonkeeper.py\nÚNICO escritor Neo4j\nEvalúa ProposedChanges\n→ Acepta/Rechaza + Commitea"]
            IDX["Indexer\nindexer.py\nChunking + embedding\n→ Qdrant snippets"]
            ANL["Analyzer\nanalyzer.py\nExtracción DSPy multi-query\n→ KnowledgePack"]
            IP_AGENT["IngestionPipeline\ningestion_pipeline.py\nCompone: self._indexer + self._analyzer\nGestiona IngestionJob\n→ MinIO + Neo4j Source"]
            WA["WorldArchitect\nworld_architect.py\nConstrucción colaborativa\n→ Entidades + Hechos vía CK"]
            NPCV["NPCVoice\nnpc_voice.py\nHabla como NPC específico\nUsa perfil + tono\n→ Respuesta en personaje"]
            RECAP["RecapAgent\nrecap_agent.py\nSintetiza historia\n→ Resúmenes de sesión"]
            SIM["SimulacrumAgent\nsimulacrum.py\nSimula facciones y NPCs\n→ Estado del mundo off-screen"]
            NPCG["NPCSceneGenerator\nnpc_scene_generator.py\nGenera escenas NPC-driven\n→ Eventos procedurales"]
        end

        subgraph AI["AI / Prompt Modules"]
            DSPY_MOD["DSPy Modules\nprompts/\n· QueryFormulation\n· KnowledgeExtraction\n· NarrativeGeneration\n· ResolutionReasoning"]
            GSR_MOD["GameSystemRuntime\ngame_system.py\nRuntime de sistema de juego\n· Resolución de stats\n· Dados + modificadores\n· Creación de personaje"]
            TOKEN["TokenBudget\ntoken_budget.py\nRanking + truncación\nPresupuesto de contexto\nPriorización de items"]
        end
    end

    STORY -->|"invoca"| SCENE
    SCENE -->|"combate detectado"| COMBAT
    STORY -->|"creación personaje"| CHAR
    SCENE -->|"modo diálogo"| CONV

    STORY --> SIM
    STORY --> RECAP
    SCENE --> CA
    SCENE --> RES
    SCENE --> NAR
    SCENE --> CK
    WORLD --> WA
    CONV --> NPCV
    CHAR --> GSR_MOD

    CA --> TOKEN
    RES --> GSR_MOD
    NAR --> DSPY_MOD
    ANL --> DSPY_MOD
    CK --> DSPY_MOD

    IP_AGENT --> IDX
    IP_AGENT --> ANL

    classDef loop fill:#c8e6c9,stroke:#388e3c,stroke-width:2px
    classDef agent fill:#fff9c4,stroke:#f9a825
    classDef ai fill:#e1bee7,stroke:#8e24aa

    class STORY,SCENE,COMBAT,CONV,WORLD,CHAR loop
    class CA,RES,NAR,CK,IDX,ANL,IP_AGENT,WA,NPCV,RECAP,SIM,NPCG agent
    class DSPY_MOD,GSR_MOD,TOKEN ai
```

```mermaid
graph TB
    subgraph L2["📦 monitor-agents"]
        subgraph LOOPS["LangGraph StateGraph Loops"]
            STORY["StoryLoop\nstory_loop.py\nState: StoryState\nGestiona campaña, invoca SceneLoop\nWorld Advance Simulacrum\nTransiciones entre escenas"]
            SCENE["SceneLoop\nscene_loop.py\nState: SceneState\nload_context → resolve → narrate\n→ persist → canonize\nMongoDBSaver checkpointing"]
            COMBAT["CombatLoop\ncombat_loop.py\nState: CombatState\ninitiative → choose → resolve\n→ narrate → check_victory\nEmbebido en SceneLoop"]
            CONV["ConversationLoop\nconversation_loop.py\nState: ConversationState\nopen → npc_response → persist\n→ close → stage_proposals\nModos: DIRECT y ACTOR"]
            WORLD["WorldBuildingLoop\nworld_building_loop.py\nState: WorldBuildingState\nload_context → process_input\n→ commit → format_response\nAuto-commitea propuestas"]
            CHAR["CharacterCreationLoop\ncharacter_creation_loop.py\nState: CharacterCreationState\nload_system → present_step\n→ await_player → process_input\nSchema-driven GSR"]
        end

        subgraph AGENTS["Specialized Agents BaseAgent"]
            CA["ContextAssembly\ncontext_assembly.py\nTri-Modal RAG:\n· Neo4j structural\n· Qdrant semantic\n· MongoDB narrative\n→ Context Package"]
            RES["Resolver\nresolver.py\nAdjudica reglas y dados\nUsa GameSystemRuntime\n→ Outcome + ProposedChanges"]
            NAR["Narrator\nnarrator.py\nGenera prosa narrativa\nUsa DSPy + instructor\n→ Immersive prose"]
            CK["CanonKeeper\ncanonkeeper.py\nÚNICO escritor Neo4j\nEvalúa ProposedChanges\n→ Acepta/Rechaza + Commitea"]
            IDX["Indexer\nindexer.py\nChunking + embedding\n→ Qdrant snippets"]
            ANL["Analyzer\nanalyzer.py\nExtracción DSPy multi-query\n→ KnowledgePack"]
            IP_AGENT["IngestionPipeline\ningestion_pipeline.py\nOrquesta Indexer + Analyzer\nGestiona IngestionJob\n→ MinIO + Neo4j Source"]
            WA["WorldArchitect\nworld_architect.py\nConstrucción colaborativa\n→ Entidades + Hechos vía CK"]
            NPCV["NPCVoice\nnpc_voice.py\nHabla como NPC específico\nUsa perfil + tono\n→ Respuesta en personaje"]
            RECAP["RecapAgent\nrecap_agent.py\nSintetiza historia\n→ Resúmenes de sesión"]
            SIM["SimulacrumAgent\nsimulacrum.py\nSimula facciones y NPCs\n→ Estado del mundo off-screen"]
            NPCG["NPCSceneGenerator\nnpc_scene_generator.py\nGenera escenas NPC-driven\n→ Eventos procedurales"]
        end

        subgraph AI["AI / Prompt Modules"]
            DSPY_MOD["DSPy Modules\nprompts/\n· QueryFormulation\n· KnowledgeExtraction\n· NarrativeGeneration\n· ResolutionReasoning"]
            GSR_MOD["GameSystemRuntime\ngame_system.py\nRuntime de sistema de juego\n· Resolución de stats\n· Dados + modificadores\n· Creación de personaje"]
            TOKEN["TokenBudget\ntoken_budget.py\nRanking + truncación\nPresupuesto de contexto\nPriorización de items"]
        end
    end

    STORY -->|"invoca"| SCENE
    SCENE -->|"combate detectado"| COMBAT
    STORY -->|"creación personaje"| CHAR
    SCENE -->|"modo diálogo"| CONV

    STORY --> SIM
    STORY --> RECAP
    SCENE --> CA
    SCENE --> RES
    SCENE --> NAR
    SCENE --> CK
    WORLD --> WA
    CONV --> NPCV
    CHAR --> GSR_MOD

    CA --> TOKEN
    RES --> GSR_MOD
    NAR --> DSPY_MOD
    ANL --> DSPY_MOD
    CK --> DSPY_MOD

    classDef loop fill:#c8e6c9,stroke:#388e3c,stroke-width:2px
    classDef agent fill:#fff9c4,stroke:#f9a825
    classDef ai fill:#e1bee7,stroke:#8e24aa

    class STORY,SCENE,COMBAT,CONV,WORLD,CHAR loop
    class CA,RES,NAR,CK,IDX,ANL,IP_AGENT,WA,NPCV,RECAP,SIM,NPCG agent
    class DSPY_MOD,GSR_MOD,TOKEN ai
```
