# MONITOR Coverage & Shape: Meta-Implementation Plan

> **For agentic workers:** This is a **meta-plan**. It decomposes a 5-area
> improvement initiative into 4 independent sub-plans. Each sub-plan
> produces working, testable software and can be executed in any order
> (though the recommended order is 1 → 2 → 4 → 3, see below).
>
> **Required sub-skill:** Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement each
> sub-plan task-by-task. Each sub-plan uses checkbox (`- [ ]`) syntax
> for tracking.

**Goal:** Lift MONITOR's ingestion coverage, graph shape, dice runtime,
multiverse hierarchy, and GM-assistant queryability from "captures
some VtM lore as a flat bag of entities" to "grounded, multi-hop,
dice-aware, queryable world model that any game system can plug into."

**Architecture:** Four independent work streams that converge on the
same shared substrate (the Neo4j graph, the Postgres llm_providers /
model_pairs / game_systems config, the Qdrant collections, the
`monitor-cli` / `monitor-ui` surfaces). They share data shapes but
do not share code modules. Each sub-plan ships its own tests and is
deployable in isolation.

**Tech Stack:** Python 3.11, FastAPI, asyncpg, motor-equivalent pymongo,
neo4j Python driver, qdrant-client, dspy-ai 3.2.1, Pydantic v2, LangGraph.

## Global Constraints

- Python 3.11, line-length 100, mypy strict (per AGENTS.md).
- Three-layer monorepo — data-layer may not import agents; agents may
  not import CLI; CLI may not import data-layer directly.
- No Neo4j writes outside CanonKeeper. Per CLAUDE.md: "Only CanonKeeper
  can write to Neo4j. All other agents create `ProposedChange` documents
  in MongoDB. CanonKeeper evaluates and commits."
- All ingestion-side improvements must be **game-system-agnostic**.
  VtM is one example; Lancer / MotW / PbtA / 7th Sea / Death in Space
  must all benefit identically.
- LLM providers, model_pairs, and bootstrap structure live in Postgres
  and are not to be touched by any of these sub-plans.
- Qdrant collections and their payload schemas are documented in
  `docs/architecture/data_model_workflow.md`; new payload fields
  must be added to `COLLECTION_CONFIGS` in `qdrant.py:47-60`.

## Investigation findings (informs the sub-plans)

Full findings report: see the conversation transcript leading to this
plan. Key gaps identified:

1. **Coverage** — `_infer_relationships` (`packages/agents/src/monitor_agents/analyzer/_core.py:3064`)
   builds family / cross-family / orphan batches. Concepts like `Beast`,
   `Caitiff`, `Clan` get only family batches (children only) and no
   global neighborhood context, so the LLM cannot infer
   `Toreador → grants → Presence` (a cross-cutting edge).

2. **Shape** — `RelationshipType` enum
   (`packages/data-layer/src/monitor_data/schemas/relationships.py:27`)
   has no `GRANTS_POWER`, `AFFECTED_BY`, `MEMBER_OF_SECT`, `BASED_IN`,
   `EMPLOYED_BY`, `IS_BACKGROUND`, `IS_TOUCHSTONE`, `HAS_MERIT`,
   `HAS_FLAW`, `PRACTICES_DISCIPLINE`. Everything collapses to
   `SUBTYPE_OF` / `MEMBER_OF` / `RELATED_TO`. Neo4j has no `:Location`,
   `:World`, `:Region`, `:Place` labels — locations are `:Entity` with
   free-text `sub_type`.

3. **Dice runtime** — `roll_dice` (`packages/data-layer/src/monitor_data/utils/dice.py:63`)
   is generic. `_execute_roll` (`resolver.py:1052`) understands
   `d20 | dice_pool` only. No willpower reroll, no hunger dice, no
   rouse check, no bane/compulsion. `ResourceEngine` has hard-coded
   regex (`resource_engine.py:91-117`) for willpower/hunger/blood
   tracking but it tracks narrative *responses*, not VtM mechanics.

4. **Multiverse hierarchy** — only `Omniverse → Multiverse → Universe →
   :Entity` populated. No `:World`, `:Region`, `:Place`, `:POI` nodes.
   `spatial_scale` is a string property, not a structural relationship.
   Snippet lineage `(:Entity)-[:HAS_SOURCE]→(:Source)` is a dead end —
   you cannot walk back to a Snippet's page number.

5. **GM assistant queryability** — the `gm_assistant` mode is declared
   in `packages/ui/backend/src/monitor_ui/routers/modes.py:60-77` with
   capabilities like "Lore recall: 'What did we establish about X?'"
   but no code path implements it. `_is_world_truth_question`
   (`resolver.py:251`) only matches `is|are|do|does|...` so "What is
   the Beast" falls through to dice-or-trivial and tries to roll
   dice. Qdrant's `knowledge` collection is written to by
   `qdrant_tools.qdrant_upsert` but no scene-loop code reads from it.

---

## Sub-plan dependency map

```
                ┌─────────────────────────────┐
                │  Sub-plan 1: Graph schema   │
                │  (relationship types +      │
                │   Location hierarchy)       │
                └──────────────┬──────────────┘
                               │ provides vocabulary
                ┌──────────────▼──────────────┐
                │  Sub-plan 2: Coverage       │
                │  (relationship-inference    │
                │   batching + global         │
                │   neighborhood +            │
                │   re-canonize pass)         │
                └──────────────┬──────────────┘
                               │ produces rich graph
                ┌──────────────▼──────────────┐
                │  Sub-plan 3: GM Assistant   │
                │  (LOOKUP intent + RAG       │
                │   explanation branch +      │
                │   /gm-assistant endpoint)   │
                └──────────────┬──────────────┘
                               │ consumes graph + retrieval
                ┌──────────────▼──────────────┐
                │  Sub-plan 4: Dice system    │
                │  (game-system-aware dice    │
                │   resolver + VtM V20 spec   │
                │   + generic-spec loader)   │
                └─────────────────────────────┘
```

**Recommended execution order:** 1 → 2 → 3 → 4. (Schema first so
coverage has vocabulary; coverage before GM assistant; dice last
because it consumes the schema for game-system fields.)

**Each sub-plan can be executed in parallel** once sub-plan 1 lands.

---

## Sub-plan 1: Graph schema expansion

**Goal:** Add the relationship types and node labels that VtM (and every
other game system) needs to express itself in the graph, generically.

**Status:** Not yet written as a task-by-task plan. Stub outline below.

**Scope:**
- Extend `RelationshipType` enum
  (`packages/data-layer/src/monitor_data/schemas/relationships.py:27`)
  with the following **game-system-agnostic** types. The vocabulary is
  built around three universal TTRPG concepts: **group** (any collective
  — clan, sect, organization, race, species, faction, party),
  **place** (any location — world, region, place, structure, landmark),
  and **resource** (any benefit/cost — discipline, feat, merit, flaw,
  background, edge, hindrance, touchstone):
  - `MEMBER_OF_GROUP` — entity belongs to a group (a vampire belongs to
    the Camarilla sect; a ranger belongs to the party; a soldier belongs
    to the army).
  - `SUBGROUP_OF_GROUP` — group is a sub-group of another group (the
    Sabbat is a sub-group of the vampire race; the fighter class is a
    sub-group of the warrior archetype; a city district is a sub-group
    of a city).
  - `LEADS_GROUP` — entity leads a group.
  - `FOUNDED_GROUP` — entity founded a group.
  - `CONTROLS_GROUP` — entity controls a group.
  - `ALLIED_WITH_GROUP` — group is allied with another group.
  - `HOSTILE_TO_GROUP` — group is hostile to another group.
  - `AFFECTED_BY` — entity is affected by something (a power, a
    condition, a curse).
  - `GRANTS_POWER` — group / role / class grants a power to its
    members.
  - `PRACTICES_DISCIPLINE` — entity practices a discipline/power.
  - `LOCATED_IN_PLACE` — entity or group is located in a place.
  - `CONTAINS_PLACE` — place contains a sub-place.
  - `IS_BACKGROUND` — entity represents a background/edge/hindrance.
  - `IS_TOUCHSTONE` — entity represents a touchstone/conviction.
  - `IS_RESOURCE` — entity is a tracked resource.
- The `Entity` sub_type vocabulary gets a `GroupType` enum (in
  `packages/data-layer/src/monitor_data/schemas/entity_subtypes.py`,
  new file): `clan, sect, organization, race, species, faction, party,
  team, crew, house, tribe, brood, coven, cult, band, gang, dynasty,
  cabal, fellowship, alliance, other`. The LLM picks from this enum
  when emitting `entity_type="organization"` or `MEMBER_OF_GROUP`/
  `SUBGROUP_OF_GROUP`/`LEADS_GROUP`/`FOUNDED_GROUP` relationships.
- The `Entity` sub_type vocabulary for locations gets a `PlaceType`
  enum: `world, plane, dimension, continent, region, kingdom, country,
  city, town, district, neighborhood, structure, building, room, landmark,
  dungeon, wilderness, other`. The LLM picks from this enum when
  emitting `entity_type="location"` or `LOCATED_IN_PLACE`/`CONTAINS_PLACE`
  relationships.
- Update `canonkeeper/agent.py` `_REL_TYPE_MAP` and `_REL_CATEGORY_MAP`
  to map LLM-side names to canonical types and pick the right category
  (taxonomic, membership, spatial, social). The LLM-side aliases
  include the obvious game-system-specific names so the LLM doesn't
  have to translate: `member_of_sect` → `MEMBER_OF_GROUP`,
  `belongs_to_clan` → `MEMBER_OF_GROUP`, `serves_in_army` →
  `MEMBER_OF_GROUP`, `practices_discipline` → `PRACTICES_DISCIPLINE`,
  `grants_power` → `GRANTS_POWER`, etc.
- Add Neo4j constraint bootstraps for any new labels
  (`packages/data-layer/src/monitor_data/db/neo4j.py:272-294`).
- Add a `Location` shape that can be World/Region/Place/POI as a
  *constrained* `sub_type` enum on `:Entity` (not a new label — keeps
  the schema flat and the tool surface small).
- Add a `spatial_scale` enum (COSMIC / PLANETARY / REGIONAL / CITY /
  BUILDING / ROOM) replacing the current free-text property.
- Update `COLLECTION_CONFIGS` in `qdrant.py:47-60` to add `sub_type`
  as a payload index on `entities` and `knowledge` collections so
  retrieval can filter by World/Region/Place/Character/Discipline/etc.
- Update `monitor-data/retrieval/pair_sync.py` if any pair config
  depends on label counts (none currently do).

**Tests:**
- Unit: `RelationshipType` enum exhaustive and round-trips.
- Unit: `_REL_TYPE_MAP` covers all enum members.
- Unit: Neo4j bootstrap creates the right constraints.
- Integration: re-ingest VtM 20th, check that new relationship types
  appear in the graph (e.g. `Clan-[:GRANTS_POWER]->Discipline`).

---

## Sub-plan 2: Coverage improvements in relationship inference

**Goal:** Make relationship inference capture the cross-cutting
edges (clan → discipline, sect → clan, location → controlled-by)
that today's family-batch approach misses.

**Status:** Not yet written as a task-by-task plan. Stub outline below.

**Scope:**
- Add a **global neighborhood batch** in
  `_infer_relationships` (`packages/agents/src/monitor_agents/analyzer/_core.py:3064`):
  for each real container (entities with children) emit one call
  that includes the container + a roster of *all* entities of the
  same `entity_type` and any entity the LLM might plausibly link to
  (sects, disciplines, paths for VtM; playbook moves for MotW; mech
  frames for Lancer). Cap at `_GLOBAL_NEIGHBORHOOD_SIZE = 50`
  per call.
- Add an **orphan rescue pass** that re-runs relationship inference
  for any concept entity that has 0 outgoing edges after the first
  pass, with a focused prompt ("this concept exists but has no
  edges — what does it relate to given the full entity roster").
- Add a **post-relationship-inference validation** in
  `assemble_and_finalize` (`_core.py:1542`) that flags orphan
  concepts (no outgoing edges, no children, not a top-level
  container) and either re-prompts or surfaces them in the
  knowledge pack's `unresolved_concepts` field for downstream UI.
- Generalize the existing few-shot examples in
  `RelationshipInferenceSignature` (`analyzer.py:1210` docstring)
  to cover the new relationship types added in sub-plan 1.
- Wire the **re-canonize pass** so that an ingestion job with
  `relationship_inference.retry=True` re-runs the relationship
  inference and rewrites the affected SUBTYPE_OF / GRANTS_POWER /
  etc. edges without re-creating entities.

**Tests:**
- Unit: global neighborhood batcher partitions the entity roster
  correctly and caps at `_GLOBAL_NEIGHBORHOOD_SIZE`.
- Unit: orphan rescue pass triggers only for entities with
  `len(outgoing_edges) == 0 AND len(children) == 0`.
- Integration: re-run relationship inference on the existing VtM
  knowledge pack (the script `scripts/_rerun_relationship_inference.py`
  already exists from the prior fix — generalize it).
- Integration: every VtM concept entity in the graph has at least
  1 outgoing edge after the rescue pass.

---

## Sub-plan 3: GM assistant queryability

**Goal:** Make "What is the Beast?", "What disciplines does Toreador
get?", "How does a contested Willpower roll work in VtM?" answerable
cleanly, grounded in canon, with a dedicated query path.

**Status:** Not yet written as a task-by-task plan. Stub outline below.

**Scope:**
- Add a new `IntentType.LOOKUP` (extend enum in
  `packages/agents/src/monitor_agents/resolver.py:303`) for
  "explain / what is / how does" questions that are neither
  world-truth yes/no nor play actions.
- Add a new `_handle_lookup` branch in `Resolver.resolve_turn`
  that:
  1. Classifies the question type (entity-explanation,
     relationship-explanation, mechanic-explanation, location-explanation).
  2. Embeds the query via `RetrievalService.embed_query`.
  3. Runs parallel Qdrant searches:
     - `entities` filtered by inferred `entity_type`.
     - `knowledge` filtered by inferred `node_type` (axiom / fact).
     - `snippets` no filter (top-k 8).
     - Optional HyDE rewrite + rerank via `PairLLM`.
  4. Builds a Neo4j traversal for relationship-explanation questions
     (e.g. "Toreador grants what" → `(:Entity {name:'Toreador'})-[:GRANTS_POWER]->(:Entity)`).
  5. Composes a structured answer with a `RAG_LORE` template that
     forces citation of source nodes.
  6. Returns a `ResolverResult` with `type="lookup"` and
     `payload={"answer": str, "citations": [...], "graph_path": [...]}`.
- Wire Qdrant `knowledge` collection into `ContextAssembly.assemble`
  (`packages/agents/src/monitor_agents/context_assembly/agent.py:245`)
  so it's read during scene context (currently only `memories` and
  `snippets` are queried).
- Add a `gm_assistant_query` tool to the `GMAgent` (`gm_agent.py`)
  with the LOOKUP intent.
- Add a `/api/gm-assistant/query` HTTP endpoint to
  `packages/ui/backend/src/monitor_ui/routers/modes.py` that
  accepts `{question, scope_universe_id, top_k}` and returns
  `{answer, citations, graph_path, confidence}`.
- Update the `modes.py:60-77` "GM Assistant" capability list to
  drop "Lore recall" from aspirational and add it as implemented.

**Tests:**
- Unit: `IntentType.LOOKUP` classification regex matches
  "what is", "what are", "explain", "how does", "tell me about"
  (without false positives on play actions).
- Unit: `_handle_lookup` returns citations in stable order.
- Integration: "What is the Beast?" returns an answer that
  cites at least 1 Source node, 1 axiom, and references the
  VtM Source PDF.
- Integration: "What disciplines does Toreador get?" returns
  an answer built from `(:Clan {name:'Toreador'})-[:GRANTS_POWER]->`
  traversal results.

---

## Sub-plan 4: Dice system + game-system-aware resolver

**Goal:** A usable, game-system-aware dice resolver that supports
willpower reroll, hunger dice, rouse check, and bane/compulsion
triggers for VtM V20, with a generic interface so other game systems
can plug in.

**Status:** Not yet written as a task-by-task plan. Stub outline below.

**Scope:**
- Add `packages/agents/src/monitor_agents/dice/` package with:
  - `base.py` — `DiceEngine` protocol: `roll(formula, *, mods) → RollResult`.
  - `generic.py` — wraps `monitor_data.utils.dice.roll_dice` (existing).
  - `vtm_v20.py` — VtM V20 dice: willpower reroll, hunger dice, rouse
    check, contested pool, blood surge, bane compulsion trigger.
  - `registry.py` — `DiceEngineRegistry` keyed by `system_name`.
- Extend `monitor_data/schemas/game_systems.py`:
  - `ResourceEngine` extension fields for tracked VtM resources
    (Blood Pool, Willpower, Health, Hunger, Humanity) with min/max
    and recovery rules.
  - `RollContext` schema: `{pool_size, difficulty, hunger, willpower_reroll, ...}`.
  - `GameSystemSpec` envelope: `{name, version, dice_engine, resources, recovery_model, action_economy, ...}`.
- Expand `packages/data-layer/src/monitor_data/defaults/systems/vampire.json`
  with the full VtM V20 spec: 13 clans, 20+ disciplines with levels,
  5 Paths of Enlightenment, 28 Abilities, 5 Attributes, 22 Backgrounds,
  Merits/Flaws, Touchstones, Convictions, Predator types, Sect structure
  (Camarilla, Sabbat, Anarch, Independent), Haven rules, Generation.
- Wire the dice engine registry into `Resolver._execute_roll` and
  `Resolver.resolve_opposed_check` so the resolver picks the
  right engine based on `scene_state.game_system`.
- Expose `vtm_contested_pool`, `vtm_rouse_check`, `vtm_willpower_reroll`
  to the `GMAgent` as MCP tools.
- Update `ResourceEngine` to charge the right resources (Willpower,
  Hunger, Blood) automatically when the VtM dice engine reports
  a reroll spend or a rouse failure.

**Tests:**
- Unit: `vtm_v20.contested_pool(5, 6, hunger=0)` returns 5 d10s,
  counts successes >= 6, no reroll, no hunger dice.
- Unit: `vtm_v20.contested_pool(5, 6, hunger=1, willpower_reroll=True)`
  rolls 5 d10s, substitutes 1 hunger die, on a failed die (not 1)
  optionally rerolls once.
- Unit: `vtm_v20.rouse_check()` rolls 1d10; success if >= 1 (which
  is "no effect"), 0 successes = Hunger +1.
- Unit: registry picks VtM engine for `system_name='Vampire: The Masquerade'`
  and falls back to generic otherwise.
- Integration: a Toreador contested Persuasion roll consumes 1
  Willpower when willpower_reroll=True and the reroll succeeds.
- Integration: `ResourceEngine` reports the right resource deltas
  in the scene turn after a rouse check failure.

---

## Cross-cutting concerns

All four sub-plans should be aware of:

- **DRY on the relationship-inference rerun path.** Sub-plan 2
  generalizes the existing `scripts/_rerun_relationship_inference.py`
  from this fix; sub-plan 3 may add a parallel rerun for the
  explanation graph; both should share the same `analyzer` and
  `canonkeeper` setup helpers.

- **No Neo4j schema changes mid-flight.** Sub-plan 1 must ship
  *before* sub-plans 2/3/4 land any writes that use new labels or
  relationship types. Use feature flags / a `monitor_meta` config
  field to gate rollout.

- **Tests are mandatory before merge.** Each sub-plan task ends
  with a green `pytest` and a green `python scripts/check_layer_dependencies.py`.
  The `pytest` run is the merge gate.

- **The `scripts/_rerun_relationship_inference.py` script** (written
  earlier in this fix) is the foundation for sub-plan 2. Generalize
  it: drop the VtM-specific name check, accept `--pack-name` and
  `--universe-id` args, write the result back to the canonical
  knowledge pack by ID.

---

## Execution handoff

**Plan complete and saved to `docs/superpowers/plans/2026-08-02-monitordm-coverage-and-shape.md`.**

This is a meta-plan. Before any sub-plan is executed, each stub section
above must be expanded into a full task-by-task plan in its own file:
- `docs/superpowers/plans/2026-08-02-monitordm-graph-schema.md`
- `docs/superpowers/plans/2026-08-02-monitordm-coverage.md`
- `docs/superpowers/plans/2026-08-02-monitordm-gm-assistant.md`
- `docs/superpowers/plans/2026-08-02-monitordm-dice-system.md`

Each sub-plan expansion follows the writing-plans skill format:
- Task files with `Files:` / `Interfaces:` / `- [ ] Step N` blocks.
- TDD: write the failing test, then the minimal implementation, then
  the commit.
- Self-review against the spec; no placeholders.

**Two execution options for the meta-plan itself:**

1. **Sub-plan-by-sub-plan (recommended)** — I expand and execute each
   stub into a full sub-plan in turn. Each sub-plan lands, ships, is
   reviewed, and you confirm before the next one starts. This keeps
   the blast radius small and lets you re-prioritize after each.

2. **Parallel expansion** — I dispatch four subagents to expand all
   four stub sections into full task-by-task plans in parallel, then
   you review and approve them all before any code changes. Faster
   to get to a unified plan document, but you commit to the design
   across all four areas before seeing the implementation.

**Which approach?**
