---
description: "How the databases interact: Neo4j, MongoDB, Qdrant, and MinIO."
tags: [architecture, data-model, database, qdrant, neo4j, mongodb]
layer: 1
---

# El Modelo de Datos: Separación de Responsabilidades

MONITOR utiliza una arquitectura políglota, empleando cuatro sistemas de bases de datos diferentes, cada uno especializado en resolver una parte específica del problema de mantener una narrativa coherente impulsada por IA.

Los agentes (Capa 2) **nunca** se conectan directamente a estas bases de datos. Todo el acceso ocurre a través de herramientas expuestas por la Capa 1 (`monitor-data-layer`) vía el protocolo MCP.

---

## 1. Neo4j: El Grafo Canónico (La Verdad Absoluta)
Neo4j es el corazón de la ontología del mundo. Almacena la "verdad canónica": entidades, lugares, facciones, relaciones y hechos.

* **Qué almacena**:
  * `EntityArchetype` (conceptos generales como "Mago" o "Espada Larga")
  * `EntityInstance` (entidades concretas como "Gandalf" o "Excalibur")
  * `Fact` y `Event` (lo que ha pasado en el mundo)
  * Relaciones direccionales (ej. `(Gandalf)-[:LOCATED_IN]->(Rivendell)`)
* **Rol**: Es la fuente definitiva de la realidad. Si no está en Neo4j, o es mentira, o es un rumor, o todavía no ha pasado.
* **Seguridad**: **Ningún agente (excepto el CanonKeeper) puede escribir en Neo4j.** Todos los demás agentes solo tienen permisos de lectura.

## 2. MongoDB: El Estado Transaccional y las Propuestas
MongoDB maneja el "estado fluido" de la partida y sirve como área de pruebas (staging) para los cambios antes de que se vuelvan oficiales.

* **Qué almacena**:
  * `ProposedChange`: Cambios propuestos por los agentes que están a la espera de ser evaluados.
  * `Session` y turnos del chat: El estado en vivo de la partida, los mensajes recientes de los jugadores, etc.
  * Documentos JSON complejos que cambian constantemente (ej. perfiles temporales de PNJ).
* **Rol**: Es la capa transaccional. Cuando el Narrador dice "Coges la espada", un agente de extracción crea un `ProposedChange` en MongoDB.
* **Flujo**: MongoDB actúa como la sala de espera. Al final de la escena, el `CanonKeeper` lee estos documentos de MongoDB, los aprueba o rechaza, y solo si son consistentes los mueve a Neo4j, actualizando el estado en MongoDB a "accepted".

### 2.1. La Puerta de Promoción de Entidades (Entity Promotion Gate)

Antes de que un `ProposedChange` de tipo `ENTITY` llegue a Neo4j necesita ganarse un UUID permanente. En vez de depender de heurísticas específicas de un sistema de juego (reconocer títulos como "Príncipe" o "Fixer" — frágil y no generaliza a otros sistemas de juego), el `CanonKeeper` aplica una puerta determinista, sin LLM, definida en `canonkeeper_support.gate_entity_proposals`:

1. **Topología (`(entity:*)` implícito)**: si otra propuesta del mismo lote (una `RELATIONSHIP`, `STATE_CHANGE` o `EVENT`) menciona esa entidad por nombre, se promueve automáticamente — el grafo exige que ambos extremos de una relación existan.
2. **Anclaje explícito (`(entity:anchor)`)**: el Narrador puede etiquetar una entidad inline como `[Nombre](entity:anchor)` en la prosa (ver `NarratorSignature`) cuando tiene peso estructural (una ficha de estadísticas, un rol de facción, un nombre al que la trama volverá). Se promueve automáticamente.
3. **Umbral de interacción (`(entity:flavor)` o sin etiquetar)**: una entidad de "decorado" (`flavor`) —o una sin etiqueta, que se trata igual por defecto— solo se promueve si `interaction_count` supera `FLAVOR_INTERACTION_THRESHOLD` (3). Por debajo del umbral se marca `REJECTED` y se descarta (garbage collection): nunca llega a ocupar espacio en Neo4j.

Esta puerta se ejecuta **antes** del pipeline de razonamiento LLM (`PolicyCheckModule` → `CanonKeeperReasoningModule` → veredicto por `instructor`). Las propuestas de tipo `ENTITY` nunca llegan a ese pipeline — quedan completamente resueltas por la puerta. El pipeline LLM sigue evaluando todas las demás propuestas (`FACT`, `RELATIONSHIP`, mecánicas, etc.) exactamente como antes.

`interaction_count` se incrementa turno a turno en `PersistenceService.merge_entity_proposals` cada vez que la misma entidad (por nombre, case-insensitive) vuelve a aparecer en la narración de la escena. Una entidad ya promovida es una **`EntityInstance`** concreta (no un `EntityArchetype` genérico) — `is_archetype=False` en el payload que `extract_new_entities` construye.

## 3. Qdrant: La Base de Datos Vectorial (Búsqueda Semántica)
Qdrant se encarga de todo lo que requiere similitud de significado (embeddings vectoriales). No entiende de reglas rígidas, entiende de cercanía conceptual.

* **Qué almacena**:
  * **Reglas y Manuales (Knowledge Packs)**: Los párrafos de los PDFs de los sistemas de juego (ej. D&D).
  * **Memoria Episódica**: Eventos pasados experimentados por los personajes (PJs y PNJs).
* **Rol**: Permite a los agentes "recordar" o "consultar" información relevante sin saturar su ventana de contexto (RAG - Retrieval-Augmented Generation).
* **Uso típico**:
  * El agente `ContextAssembly` busca reglas (ej. "¿Cómo funciona el veneno?") usando `qdrant_search`.
  * El agente `NPCVoice` busca recuerdos (ej. "¿He visto a este jugador antes?") usando `qdrant_search_memories`.

## 4. MinIO: Almacenamiento de Objetos (Blobs)
MinIO es un servidor compatible con S3 que almacena archivos binarios o grandes que no pertenecen a una base de datos estructurada.

* **Qué almacena**:
  * PDFs de manuales de rol, imágenes subidas por los usuarios, avatares de personajes, etc.
* **Rol**: Es el punto de entrada para el pipeline de ingesta. Cuando el usuario sube un PDF, va a MinIO. Luego, el agente `Indexer` lo lee de MinIO, lo parsea, y envía sus fragmentos a Qdrant y sus conceptos a Neo4j.

## 5. PostgreSQL (Metadatos del Sistema)
PostgreSQL se utiliza para la configuración técnica de la infraestructura (gestión de colecciones, prefijos de bases de datos, asignaciones técnicas de los inquilinos) y no para el estado del juego per se.

---

## El Flujo Completo en Acción

Imagina que un jugador dice: *"Reviso el cofre y saco la Gema del Alma, recordando que el rey la mencionó."*

1. **MinIO / Qdrant**: El agente `ContextAssembly` busca en **Qdrant** las reglas sobre cómo funcionan las Gemas del Alma (ingresadas previamente de un PDF en **MinIO**).
2. **Neo4j (Lectura)**: El agente verifica en **Neo4j** si "Gema del Alma" existe en esa habitación.
3. **MongoDB (Escritura)**: El agente de extracción crea un `ProposedChange` en **MongoDB**: *"El jugador ahora tiene la Gema del Alma"*.
4. **Qdrant (Escritura)**: Se guarda un recuerdo en **Qdrant**: *"El jugador encontró la gema"*, para que los PNJs puedan buscarlo después (`qdrant_embed_memory`).
5. **CanonKeeper**: Al final del turno/escena, evalúa el `ProposedChange` en **MongoDB**. Si es válido, lo oficializa creando el nodo/relación definitiva en **Neo4j** y actualizando MongoDB.
