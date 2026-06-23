# MONITOR — Diagramas de Arquitectura

> Colección completa de diagramas de ingeniería del sistema MONITOR.
> C4 Model, i*, secuencias, máquinas de estado, y macro-diagrama.

---

## Índice de Diagramas

| # | Archivo | Tipo | Qué muestra | Revisado |
|---|---------|------|-------------|----------|
| 1 | [01-macro-diagram.md](01-macro-diagram.md) | Vista total | TODO el sistema en un canvas | ✅ |
| 2 | [02-c4-context.md](02-c4-context.md) | C4 Nivel 1 | Usuarios, MONITOR, LLMs externos | ✅ |
| 3 | [03-c4-containers.md](03-c4-containers.md) | C4 Nivel 2 | 3 capas + 5 DBs + MCP | ✅ |
| 4 | [04-c4-data-layer.md](04-c4-data-layer.md) | C4 Nivel 3 | MCP tools, DB clients, schemas, middleware | ✅ |
| 5 | [05-c4-agent-layer.md](05-c4-agent-layer.md) | C4 Nivel 3 | Agentes, loops, DSPy, GameSystemRuntime | ✅ |
| 6 | [06-istar-sd.md](06-istar-sd.md) | i* SD | Actores → objetivos → MONITOR | ✅ |
| 7 | [07-istar-sr.md](07-istar-sr.md) | i* SR | Descomposición interna de objetivos | ✅ |
| 8 | [08-ingestion-pipeline.md](08-ingestion-pipeline.md) | Secuencia | Archivo → MinIO → Indexer → Analyzer → CanonKeeper | ✅ |
| 9 | [09-gameplay-turn.md](09-gameplay-turn.md) | Secuencia | Player → SceneLoop → ContextAssembly → Resolver → Narrator → CanonKeeper | ✅ |
| 10 | [10-langgraph-loops.md](10-langgraph-loops.md) | State machines | Story, Scene, Combat, Conversation, WorldBuilding, CharacterCreation | ✅ |
| 11 | [11-control-data-flow.md](11-control-data-flow.md) | Flujo | Loops anidados, roles de DB, authority boundaries | ✅ |

---

## Guía de Lectura

### Si solo ves uno...
→ [**01-macro-diagram.md**](01-macro-diagram.md) — el canvas completo.

### Si quieres entender la arquitectura...
→ Sigue el orden C4: [02](02-c4-context.md) → [03](03-c4-containers.md) → [04](04-c4-data-layer.md) → [05](05-c4-agent-layer.md)

### Si quieres entender los flujos...
→ [08](08-ingestion-pipeline.md) (cómo entra el conocimiento) → [09](09-gameplay-turn.md) (cómo se juega) → [10](10-langgraph-loops.md) (máquinas de estado)

### Si quieres entender los objetivos del sistema...
→ [06](06-istar-sd.md) (dependencias estratégicas) → [07](07-istar-sr.md) (descomposición interna)

### Si necesitas el panorama operativo...
→ [11](11-control-data-flow.md) (jerarquía de loops + DB roles + authority)

---

## Convenciones de Color

| Color | Significado |
|-------|-------------|
| 🟣 Rosa | Usuarios / Actores |
| 🔵 Azul claro | Capa 3: Interface (CLI / Web UI) |
| 🟢 Verde | Capa 2: Agents (loops + agentes + AI modules) |
| 🟠 Naranja | Capa 1: Data Layer (MCP tools + DB clients + schemas) |
| 🟣 Púrpura | Infrastructure (Neo4j, MongoDB, Qdrant, PostgreSQL, MinIO) |
| 🔴 Rojo claro | Externos (LLM Providers) |
| 🟡 Amarillo | Authority Middleware / Boundary enforcement |

---

## Conceptos Clave del Sistema

| Concepto | Implementación |
|----------|---------------|
| **Arquitectura** | 3 capas estrictas: CLI/UI → Agents → Data Layer |
| **Comunicación** | MCP (Model Context Protocol) entre capas |
| **Orquestación** | LangGraph StateGraph con MongoDBSaver checkpointing |
| **Loops** | 6 loops: Story, Scene, Combat, Conversation, WorldBuilding, CharacterCreation |
| **Agentes** | 12 agentes especializados stateless (BaseAgent) |
| **Patrón Clave** | ProposedChange: solo CanonKeeper escribe Neo4j |
| **RAG** | Tri-Modal: Neo4j (estructural) + Qdrant (semántico) + MongoDB (narrativo) |
| **Ingestión** | Archivo → MinIO → Indexer → Qdrant → Analyzer → KnowledgePack → CanonKeeper |
| **IA** | DSPy + instructor + LiteLLM para prompts, extracción y abstracción de proveedor |
| **Persistencia** | 5 DBs: Neo4j (verdad), MongoDB (narrativa), Qdrant (vectores), PostgreSQL (config), MinIO (archivos) |
| **Durabilidad** | MongoDBSaver checkpointing en todos los loops |
| **Autoridad** | Authority Middleware: matriz de permisos por tipo de agente |

---

> **Fuente**: Estos diagramas fueron generados a partir del análisis del código fuente en `packages/` y verificados contra los documentos de arquitectura en `docs/architecture/`.
> **Última actualización**: 2026-05-03
