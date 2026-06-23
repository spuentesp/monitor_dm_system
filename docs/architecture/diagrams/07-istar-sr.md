# 07 — i* Strategic Rationale (SR)

> Descomposición interna de objetivos del sistema MONITOR.
> Muestra cómo cada goal de alto nivel se descompone en sub-objetivos,
> tareas técnicas, y dependencias compartidas.

## Descripción

El modelo i* Strategic Rationale (SR) abre la caja negra de MONITOR y muestra
la estructura interna de goals, tasks, resources, y soft-goals.

### Estructura de Goals

| Goal | Sub-objetivos | Dependencias técnicas |
|------|---------------|----------------------|
| G1: Memoria Persistente | Tri-Modal Recall, ContextAssembly, TokenBudget | — |
| G2: Consistencia Canónica | CanonKeeper, ProposedChange Pattern, Authority Middleware | — |
| G3: Narrativa Fluida | Narrator, Resolver, SceneLoop, StoryLoop | MongoDBSaver, LiteLLM, DSPy, GameSystemRuntime |
| G4: Ingesta de Conocimiento | IngestionPipeline, Indexer, Analyzer, KnowledgePack | LiteLLM, DSPy |
| G5: Mundo Vivo | SimulacrumAgent, NPCSceneGenerator, WorldBuildingLoop | LiteLLM |

### Dependencias Compartidas

- **LiteLLM**: Usado por Narrator, Resolver, Analyzer, CanonKeeper, SimulacrumAgent, WorldArchitect, NPCVoice — todos los agentes que llaman LLMs
- **DSPy**: Usado por Narrator, Analyzer, CanonKeeper, Resolver — agentes que necesitan razonamiento creativo estructurado
- **GameSystemRuntime**: Usado por Resolver y CharacterCreationLoop
- **MongoDBSaver**: Usado por SceneLoop y StoryLoop para checkpointing

## Diagrama

```mermaid
graph TB
    subgraph BOUNDARY["🎲 MONITOR System Boundary"]
        ROOT["🎯 NarrativeIntelligence\nProveer experiencia narrativa\ncoherente, persistente y con reglas"]

        subgraph G1["Objetivo: Memoria Persistente"]
            G1_1["Tri-Modal Recall\nNeo4j + Qdrant + MongoDB"]
            G1_2["ContextAssembly\nEnsamblar contexto por turno"]
            G1_3["TokenBudget\nPriorizar y truncar contexto"]
        end

        subgraph G2["Objetivo: Consistencia Canónica"]
            G2_1["CanonKeeper\nÚnico escritor de Neo4j"]
            G2_2["ProposedChange Pattern\nCambios staged en MongoDB"]
            G2_3["Authority Middleware\nMatriz de permisos"]
        end

        subgraph G3["Objetivo: Narrativa Fluida"]
            G3_1["Narrator\nGeneración de prosa (DSPy)"]
            G3_2["Resolver\nAdjudicación de reglas"]
            G3_3["SceneLoop\nMáquina de estados de turnos"]
            G3_4["StoryLoop\nProgresión de campaña"]
        end

        subgraph G4["Objetivo: Ingesta de Conocimiento"]
            G4_1["IngestionPipeline\nOrquestador de ingesta"]
            G4_2["Indexer\nChunking + embedding"]
            G4_3["Analyzer\nExtracción DSPy"]
            G4_4["KnowledgePack\nPaquete revisable en MongoDB"]
        end

        subgraph G5["Objetivo: Mundo Vivo"]
            G5_1["SimulacrumAgent\nSimulación de facciones"]
            G5_2["NPCSceneGenerator\nEscenas procedurales"]
            G5_3["WorldBuildingLoop\nCreación colaborativa"]
        end

        subgraph TASKS["Tareas Técnicas (compartidas)"]
            T1["MongoDBSaver\nCheckpoint de loops\n(SceneLoop, StoryLoop)"]
            T2["LiteLLM\nAbstracción de proveedor\n(Narrator, Resolver, Analyzer,\nCanonKeeper, Simulacrum,\nWorldArchitect, NPCVoice)"]
            T3["DSPy Optimization\nOptimización de prompts\n(Narrator, Analyzer,\nCanonKeeper, Resolver)"]
            T4["GameSystemRuntime\nMotor de reglas genérico\n(Resolver, CharacterCreation)"]
        end
    end

    ROOT --> G1
    ROOT --> G2
    ROOT --> G3
    ROOT --> G4
    ROOT --> G5

    G1 --> G1_1
    G1 --> G1_2
    G1 --> G1_3
    G2 --> G2_1
    G2 --> G2_2
    G2 --> G2_3
    G3 --> G3_1
    G3 --> G3_2
    G3 --> G3_3
    G3 --> G3_4
    G4 --> G4_1
    G4 --> G4_2
    G4 --> G4_3
    G4 --> G4_4
    G5 --> G5_1
    G5 --> G5_2
    G5 --> G5_3

    G3_3 --> T1
    G3_4 --> T1
    G3_1 --> T2
    G3_1 --> T3
    G3_2 --> T4
    G3_2 --> T2
    G4_3 --> T2
    G4_3 --> T3
    G2_1 --> T2
    G2_1 --> T3
    G5_1 --> T2

    classDef root fill:#e8eaf6,stroke:#3f51b5,stroke-width:3px
    classDef goal fill:#c8e6c9,stroke:#388e3c,stroke-width:2px
    classDef task fill:#fff9c4,stroke:#f9a825
    classDef bound fill:#fafafa,stroke:#999,stroke-dasharray: 5 5

    class ROOT root
    class G1,G2,G3,G4,G5 goal
    class T1,T2,T3,T4 task
```
