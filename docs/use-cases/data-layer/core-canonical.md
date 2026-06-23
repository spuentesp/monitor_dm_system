## DL-1: Manage Multiverse/Universes (Neo4j)
- Inputs: name, description, tags, parent_id (optional).
- Behavior: create/update/list/delete Universe nodes; validate unique name per parent; maintain HAS_UNIVERSE hierarchy.
- Cross-refs: Axioms, Sources, Entities, Stories link to Universe.
- Outputs: Universe record with id, hierarchy and tags.

## DL-2: Manage Archetypes & Instances (Neo4j)
- Inputs: universe_id, name, entity_type, description, properties, state_tags (instances), archetype_id (instances).
- Behavior: CRUD EntityArchetype/EntityInstance; maintain DERIVES_FROM (instance→archetype); enforce entity_type enum; state_tags only on instances.
- Cross-refs: Relationships, Facts/Events, PlotThreads, Scenes/Turns (participants), Memories.
- Outputs: Entity records with IDs and links.

## DL-3: Manage Facts & Events (Neo4j, provenance)
- Inputs: universe_id, statement/title, fact_type, entities involved, properties, source_ids/scene_ids/snippet_ids, canon_level/confidence, timestamps for timeline.
- Behavior: CRUD facts/events; SUPPORTED_BY edges to Source/Snippet/Scene; INVOLVES/ABOUT edges to entities; optional NEXT/BEFORE/AFTER timeline ordering; enforce canon_level enum.
- Cross-refs: Query/timeline views, provenance chains, PlotThreads.
- Outputs: Fact/Event records with provenance and timeline anchors.

## DL-4: Manage Stories, Scenes, Turns (Neo4j + MongoDB)
- Inputs: story metadata (Neo4j), scene/turn payloads (MongoDB), status transitions.
- Behavior: Create/update Story (Neo4j canonical container); Create/update/list Scene (MongoDB narrative), append Turns; optional canonical Scene node in Neo4j; enforce statuses.
- Cross-refs: Scenes link to Story, locations, participating entities; Turns reference Scene; Facts/Events may reference Scene.
- Outputs: Story IDs; scene/turn documents; status updates.

## DL-5: Manage Proposed Changes (MongoDB)
- Inputs: change_type (fact/entity/relationship/state_change/event), content payload, confidence/status, scope IDs (scene/story/universe).
- Behavior: CRUD ProposedChange; enforce change_type enum; status transitions (pending→accepted/rejected); preserve evidence refs.
- Cross-refs: Canonization consumes these; links to Scene/Story/Universe and Entities.
- Outputs: ProposedChange documents with IDs and status.

## DL-6: Manage Story Outlines & Plot Threads (MongoDB + Neo4j)
- Inputs:
  - Story Outline: story_id, theme, premise, constraints, beats[], structure_type, template, branching_points[], mystery_structure
  - Story Beat: beat_id, title, description, order, status, optional, related_threads[], required_for_threads[]
  - Mystery Structure: truth, question, core_clues[], bonus_clues[], red_herrings[], suspects[], current_player_theories[]
  - Plot Thread: story_id, title, thread_type, status, priority, urgency, deadline, scene_ids[], entity_ids[], foreshadowing_events[], revelation_events[], payoff_status, player_interest_level, gm_importance
- Behavior:
  - MongoDB: CRUD story_outline docs with beat manipulation (add, remove, update, reorder); track mystery clue discovery; auto-calculate pacing metrics (tension, completion, act progression); support branching narratives
  - Neo4j: CRUD PlotThread nodes with 5 relationship types (HAS_THREAD to Story, ADVANCED_BY to Scenes, INVOLVES to Entities, FORESHADOWS from Events, REVEALS from Events); track priority, urgency, deadlines; monitor foreshadowing/payoff status; filter by story/type/status/priority/entity
- Cross-refs: Story, Scenes, Entities, Facts/Events, Turns (beat completion tracking).
- Outputs:
  - Story outline docs with beats, mystery structure, pacing metrics, branching points
  - PlotThread nodes with all relationships and tracking metadata
  - Beat progression status (pending/in_progress/completed/skipped)
  - Clue discovery tracking (hidden/discovered/revealed)
  - Pacing analysis (estimated_completion, tension_level, scenes_since_major_event)

## DL-7: Manage Memories (MongoDB + Qdrant)
- Inputs: entity_id, text, scene_id/fact_id (optional), importance, metadata.
- Behavior: CRUD CharacterMemory docs (MongoDB); embed/recall via Qdrant; enforce importance range.
- Cross-refs: Entities, Scenes/Facts; Qdrant vectors keyed by memory_id/entity_id.
- Outputs: Memory docs; vector IDs; recall results.

## DL-8: Manage Sources, Documents, Snippets, Ingest Proposals (MongoDB + Neo4j)
- Inputs: source (title/type/canon_level/authority), document (minio_ref/filename/file_type), snippet (text/page), ingest proposals (proposal_type/content/confidence/status, evidence_snippet_ids).
- Behavior: CRUD Source (Neo4j) and Document/Snippet/IngestProposal (MongoDB); link Source to Universe; enforce proposal status; store evidence links; maintain provenance chains.
- Cross-refs: Facts/Axioms supported_by Source/Snippet; ingest pipeline consumes/creates proposals; Documents reference MinIO object.
- Outputs: IDs for source/doc/snippet/proposals; provenance links.

## DL-9: Manage Binary Assets (MinIO)
- Inputs: bucket/key/content-type/size/metadata, optional source_id/universe_id.
- Behavior: upload/download/delete/list objects; preserve metadata; return references (bucket/key).
- Cross-refs: Documents/Sources store minio_ref; ingest pipeline links binaries to sources.
- Outputs: Object reference and metadata.

## DL-10: Vector Index Operations (Qdrant)
- Inputs: payload (id, collection, vector, metadata including story_id/scene_id/entity_id/type).
- Behavior: upsert/search/delete embeddings; enforce collection names; return scored matches.
- Cross-refs: Scenes, Memories, Snippets; CLI/query uses these for semantic search.
- Outputs: Qdrant operation result; search hits with payload.

## DL-11: Text Search Index Operations (OpenSearch)
- Inputs: index name, document body (id, type, universe_id, text/snippet), query with filters.
- Behavior: index/update/delete documents; keyword search with filters; return highlights/snippets.
- Cross-refs: Sources/Snippets/Facts/Docs.
- Outputs: index ack; search hits with snippet and metadata.

## DL-12: MCP Server & Middleware (Auth/Validation/Health)
- Inputs: tool registry, authority matrix, schema validators.
- Behavior: register tools; apply auth and validation; expose health/status endpoint.
- Outputs: MCP tool list; health status.

## DL-13: Manage Axioms (Neo4j)
- Inputs: universe_id, statement, domain, confidence/canon_level/authority, source_ids/snippet_ids.
- Behavior: CRUD Axiom nodes; link to Universe and Source/Snippet via SUPPORTED_BY; enforce enums.
- Cross-refs: Facts and rules reasoning; documentation of world rules.
- Outputs: Axiom records with provenance.

## DL-14: Manage Relationships & State Tags (Neo4j)
- Inputs: from_id, to_id, rel_type, properties; state_tags updates (entity_id, tags).
- Behavior: CRUD relationships (membership/ownership/social/spatial/participation/etc.); update state_tags on EntityInstance; enforce rel_type enum; prevent invalid IDs.
- Cross-refs: Entities, Facts/Events, Scenes, PlotThreads.
- Outputs: Relationship records; updated entity state tags.

---
