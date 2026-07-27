---
description: "Differentiates between templates and actualized objects."
tags: [ontology, entities]
layer: 1
---

# Entity Types (Archetypes vs. Instances)

MONITOR cleanly separates definitions (what a thing *could* be) from actualized beings (what a thing *is*).

## Archetypes
- **Definition**: A blueprint or template.
- **Example**: "Goblin (Monster Manual)", "Longsword (Standard Item)".
- **Usage**: Used heavily by Knowledge Packs.

## Instances
- **Definition**: A specific, unique realization in the world.
- **Example**: "Droop the Goblin (currently at 3 HP)", "Elara's Longsword (chipped edge)".
- **Usage**: Used during live play. Instances inherit baseline traits from their Archetype but can mutate independently.

## Entity Promotion: Anchor vs. Flavor

Not every named entity a narrator invents during play deserves a permanent Neo4j `EntityInstance`. Promotion is game-system-agnostic and gated on **structural intent and topology**, not on lore-specific heuristics (no more matching titles like "Prince" or "Fixer" — that approach doesn't generalize from Vampire to Cyberpunk RED or any other system).

The Narrator tags a newly-introduced named entity inline, on first mention only:

- **`[Name](entity:anchor)`** — this entity has structural weight: a stat block, a faction role, a name the plot will return to. Promoted to Neo4j automatically, as an **Instance** (`is_archetype=False`) — it's a concrete realization born from play, not a reusable template.
- **`[Name](entity:flavor)`** — disposable scene dressing (a bored bartender, an unnamed guard) with no mechanical future. Promoted only if it turns out to matter later (see Garbage Collection below); otherwise discarded.
- **Untagged** — an entity mentioned without a tag is treated the same as `flavor` by default.

### Topology overrides the tag

Regardless of tag (or lack of one), an entity referenced by a `RELATIONSHIP`, `STATE_CHANGE`, or `EVENT` proposal in the same batch is promoted immediately — Neo4j's own graph-integrity requirement (a relationship needs two real endpoints) is itself a promotion signal, and takes priority over the anchor/flavor distinction.

### Flavor Garbage Collection

A `flavor`-tagged (or untagged) entity's `interaction_count` — how many turns of the scene it's been mentioned in — is tracked on its `ProposedChange`. If that count exceeds a threshold (`FLAVOR_INTERACTION_THRESHOLD = 3`, see `canonkeeper_support.py`) before the scene evaluates, the entity is promoted anyway: sustained narrative presence is itself evidence of importance, tag or no tag. Below the threshold, `CanonKeeper` marks it `REJECTED` and it is discarded — it never occupies a Neo4j node. This keeps the graph free of one-line background characters while still catching an entity that quietly became a recurring presence.

See [`docs/2_architecture/data_model_workflow.md`](../2_architecture/data_model_workflow.md#21-la-puerta-de-promoción-de-entidades-entity-promotion-gate) for the full mechanism (the promotion gate runs before, and instead of, CanonKeeper's LLM evaluation pipeline for `ENTITY` proposals).

## See Also
- [Ontology Index](./_index.md)
