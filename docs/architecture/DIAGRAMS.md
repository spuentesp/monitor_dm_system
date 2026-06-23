# MONITOR — Arquitectura Visual

> **⚠️ Este archivo es un índice.** Los diagramas completos con explicaciones están en `diagrams/`.

---

## Índice de Diagramas

| # | Archivo | Tipo | Qué muestra |
|---|---------|------|-------------|
| 1 | [diagrams/01-macro-diagram.md](diagrams/01-macro-diagram.md) | Vista total | TODO el sistema en un canvas |
| 2 | [diagrams/02-c4-context.md](diagrams/02-c4-context.md) | C4 Nivel 1 | Usuarios, MONITOR, LLMs externos |
| 3 | [diagrams/03-c4-containers.md](diagrams/03-c4-containers.md) | C4 Nivel 2 | 3 capas + 5 DBs + MCP |
| 4 | [diagrams/04-c4-data-layer.md](diagrams/04-c4-data-layer.md) | C4 Nivel 3 | MCP tools, DB clients, schemas, middleware |
| 5 | [diagrams/05-c4-agent-layer.md](diagrams/05-c4-agent-layer.md) | C4 Nivel 3 | Agentes, loops, DSPy, GameSystemRuntime |
| 6 | [diagrams/06-istar-sd.md](diagrams/06-istar-sd.md) | i* SD | Actores → objetivos → MONITOR |
| 7 | [diagrams/07-istar-sr.md](diagrams/07-istar-sr.md) | i* SR | Descomposición interna de objetivos |
| 8 | [diagrams/08-ingestion-pipeline.md](diagrams/08-ingestion-pipeline.md) | Secuencia | Archivo → MinIO → Indexer → Analyzer → CanonKeeper |
| 9 | [diagrams/09-gameplay-turn.md](diagrams/09-gameplay-turn.md) | Secuencia | Player → SceneLoop → ContextAssembly → Resolver → Narrator → CanonKeeper |
| 10 | [diagrams/10-langgraph-loops.md](diagrams/10-langgraph-loops.md) | State machines | Story, Scene, Combat, Conversation, WorldBuilding, CharacterCreation |
| 11 | [diagrams/11-control-data-flow.md](diagrams/11-control-data-flow.md) | Flujo | Loops anidados, roles de DB, authority boundaries |

---

## Guía de Lectura

- **Un solo diagrama** → [01-macro-diagram.md](diagrams/01-macro-diagram.md)
- **Arquitectura C4** → [02](diagrams/02-c4-context.md) → [03](diagrams/03-c4-containers.md) → [04](diagrams/04-c4-data-layer.md) → [05](diagrams/05-c4-agent-layer.md)
- **Flujos** → [08](diagrams/08-ingestion-pipeline.md) → [09](diagrams/09-gameplay-turn.md) → [10](diagrams/10-langgraph-loops.md)
- **Objetivos** → [06](diagrams/06-istar-sd.md) → [07](diagrams/07-istar-sr.md)
- **Operativo** → [11](diagrams/11-control-data-flow.md)

---

> **Última actualización**: 2026-05-03 — Verificados contra código fuente en `packages/`.