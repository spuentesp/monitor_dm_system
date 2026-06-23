# 06 — i* Strategic Dependency (SD)

> Modelo de dependencias estratégicas entre actores y MONITOR.
> Muestra qué necesita cada actor del sistema y de qué dependencias externas depende MONITOR.

## Descripción

El modelo i* Strategic Dependency (SD) modela las relaciones de dependencia entre actores.
Cada flecha `D:` representa una dependencia: el actor origen depende del actor destino
para satisfacer un objetivo.

### Actores

| Actor | Objetivo principal |
|-------|-------------------|
| Jugador | Vivir una historia inmersiva con decisiones significativas |
| Game Master | Asistencia narrativa con coherencia del mundo |
| World Architect | Mundos consistentes creados desde setting books |

### Goals de MONITOR

| Goal | Descripción | Depende de |
|------|-------------|-----------|
| NarrativeExperience | Experiencia narrativa fluida | LLM Provider, MongoDB (contexto narrativo) |
| WorldConsistency | Verdad canónica sin contradicciones | Neo4j |
| PersistentMemory | Recordar todo lo relevante | Neo4j (estructural) + MongoDB (narrativo) + Qdrant (semántico) |
| RulesAdjudication | Aplicar reglas justamente | LLM Provider |
| KnowledgeIngestion | Extraer conocimiento de fuentes | LLM Provider |
| WorldBuilding | Crear mundos coherentes | LLM Provider |

## Diagrama

```mermaid
graph TB
    subgraph ACTORS["🎭 Actores"]
        PLAYER["👤 Jugador\nQuiere: vivir una historia inmersiva\nObjetivo: decisiones significativas"]
        GM["👤 Game Master\nQuiere: asistencia narrativa\nObjetivo: coherencia del mundo"]
        ARCHITECT["👤 World Architect\nQuiere: mundos consistentes\nObjetivo: ingestar setting books"]
    end

    subgraph MONITOR["🎲 MONITOR"]
        NARRATIVE["NarrativeExperience\nMeta: experiencia narrativa fluida"]
        CONSISTENCY["WorldConsistency\nMeta: verdad canónica sin contradicciones"]
        MEMORY["PersistentMemory\nMeta: recordar todo lo relevante"]
        RULES["RulesAdjudication\nMeta: aplicar reglas justamente"]
        INGESTION["KnowledgeIngestion\nMeta: extraer conocimiento de fuentes"]
        WORLDBUILD["WorldBuilding\nMeta: crear mundos coherentes"]
    end

    subgraph EXTERNAL["☁️ Dependencias Externas"]
        LLM_SERVICE["LLM Provider\nMeta: inferencia de lenguaje\n(OpenAI, Anthropic, Gemini, Local)"]
        NEO4J_DB["Neo4j\nMeta: grafo canónico\n(verdad, consistencia)"]
        MONGO_DB["MongoDB\nMeta: memoria narrativa\n(turnos, escenas, propuestas)"]
        QDRANT_DB["Qdrant\nMeta: recall semántico\n(vectores, embeddings)"]
    end

    PLAYER -->|"D: experiencia narrativa"| NARRATIVE
    PLAYER -->|"D: reglas justas"| RULES
    GM -->|"D: consistencia del mundo"| CONSISTENCY
    GM -->|"D: memoria persistente"| MEMORY
    ARCHITECT -->|"D: ingesta de setting"| INGESTION
    ARCHITECT -->|"D: creación de mundos"| WORLDBUILD

    NARRATIVE -->|"D: inferencia LLM"| LLM_SERVICE
    RULES -->|"D: inferencia LLM"| LLM_SERVICE
    INGESTION -->|"D: inferencia LLM"| LLM_SERVICE
    WORLDBUILD -->|"D: inferencia LLM"| LLM_SERVICE

    CONSISTENCY -->|"D: verdad canónica"| NEO4J_DB
    MEMORY -->|"D: grafo estructural"| NEO4J_DB
    MEMORY -->|"D: narrativa textual"| MONGO_DB
    MEMORY -->|"D: recall semántico"| QDRANT_DB
    NARRATIVE -->|"D: contexto narrativo"| MONGO_DB

    classDef actor fill:#08427b,stroke:#052e56,color:#fff
    classDef goal fill:#e8f5e9,stroke:#388e3c
    classDef external fill:#ffebee,stroke:#c62828

    class PLAYER,GM,ARCHITECT actor
    class NARRATIVE,CONSISTENCY,MEMORY,RULES,INGESTION,WORLDBUILD goal
    class LLM_SERVICE,NEO4J_DB,MONGO_DB,QDRANT_DB external
```

```mermaid
graph TB
    PLAYER["👤 Jugador"]
    GM["👤 Game Master"]
    ARCHITECT["👤 World Architect"]
    MONITOR["🎲 MONITOR"]

    PLAYER -->|"inmersión narrativa ⊏\n(juego solo)"| MONITOR
    PLAYER -->|"resolución justa ⟶"| MONITOR
    PLAYER -->|"elecciones con consecuencias ⤳"| MONITOR

    GM -->|"asistencia creativa ⊏\n(no reemplazo)"| MONITOR
    GM -->|"continuidad canónica ⟶"| MONITOR
    GM -->|"gestión de NPCs ⤳"| MONITOR

    ARCHITECT -->|"ingesta eficiente ⤳"| MONITOR
    ARCHITECT -->|"consistencia ontológica ⟶"| MONITOR
    ARCHITECT -->|"blast radius ◁\n(cambio propaga)"| MONITOR

    MONITOR -->|"narrativa coherente ⊏"| PLAYER
    MONITOR -->|"mundos jugables ⟶"| ARCHITECT

    classDef actor fill:#08427b,stroke:#052e56,color:#fff
    classDef system fill:#1168bd,stroke:#0b4884,color:#fff

    class PLAYER,GM,ARCHITECT actor
    class MONITOR system
```
