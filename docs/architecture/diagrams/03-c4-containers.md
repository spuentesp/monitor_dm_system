# 03 — C4 Contenedores (Nivel 2)

> Diagrama de contenedores del sistema MONITOR.
> Muestra las aplicaciones, servicios y bases de datos que componen el sistema.

## Descripción

MONITOR se despliega como 4 contenedores de aplicación + 5 bases de datos:

| Contenedor | Tecnología | Responsabilidad |
|-----------|-----------|----------------|
| CLI | Python (Typer) | Comandos: play, ingest, manage |
| Web UI | FastAPI + Next.js | Chat API, WebSocket, REST |
| Agents | Python (LangGraph + DSPy) | Loops + agentes especializados, stateless |
| MCP Server | Python (STDIO/HTTP) | Exposición de herramientas, authority middleware |

**Comunicación entre capas**:
- CLI → MCP Server: vía MCP stdio
- Web UI → Agents: import directo (mismo proceso)
- Agents → MCP Server: vía MCP stdio

## Diagrama

```mermaid
graph TB
    subgraph USERS["👤 Usuarios"]
        P["Jugador"]
        G["GM"]
        A["World Architect"]
    end

    subgraph MONITOR["🎲 MONITOR System"]
        subgraph L3["Capa 3: Interface"]
            CLI["CLI Container\nTyper · Python\nComandos: play, ingest, manage"]
            WEB["Web UI Container\nFastAPI + Next.js\nChat API · WebSocket · REST"]
        end

        subgraph L2["Capa 2: Agents"]
            AGENTS_CONTAINER["Agents Container\nPython · LangGraph · DSPy\n6 Loops + 12 Agentes\nStateless workers\nMongoDBSaver checkpointing"]
        end

        subgraph L1["Capa 1: Data Layer"]
            MCP_SERVER["MCP Server Container\nPython · STDIO/HTTP\nExposición de herramientas\nAuthority Middleware\n8 grupos de MCP tools"]
        end

        subgraph DB["Bases de Datos"]
            N4J[("Neo4j\nGrafo Canónico\nEntidades · Hechos · Relaciones")]
            MONGO[("MongoDB\nMemoria Narrativa\nTurnos · Escenas · Propuestas\nWorking State · Chat Sessions")]
            QDR[("Qdrant\nMotor de Recall\nVectores · Embeddings")]
            PG[("PostgreSQL\nPlano de Control\nProviders · Config · Schemas")]
            MINIO[("MinIO\nObject Storage\nPDFs · EPUBs · Fuentes")]
        end
    end

    P --> WEB
    G --> WEB
    G --> CLI
    A --> CLI

    CLI -->|"MCP stdio"| MCP_SERVER
    WEB -->|"import directo"| AGENTS_CONTAINER
    AGENTS_CONTAINER -->|"MCP stdio"| MCP_SERVER

    MCP_SERVER --> N4J
    MCP_SERVER --> MONGO
    MCP_SERVER --> QDR
    MCP_SERVER --> PG
    MCP_SERVER --> MINIO

    classDef container fill:#438dd5,stroke:#2e6295,color:#fff
    classDef db fill:#6b4c9a,stroke:#4a3570,color:#fff

    class CLI,WEB,AGENTS_CONTAINER,MCP_SERVER container
    class N4J,MONGO,QDR,PG,MINIO db
```
