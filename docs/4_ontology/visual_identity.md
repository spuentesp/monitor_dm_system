---
description: "VisualIdentity — the structured, canon-aware description of a subject's appearance, with anchor shapes, precedence, and the CanonKeeper boundary."
tags: [ontology, visual-identity, canon, canonkeeper, generated-asset]
layer: 1
---

# Visual Identity

A `VisualIdentity` is a structured, canon-aware description of how a
subject appears. It feeds the image-generation prompt builder with stable
appearance cues (hair, eyes, attire, palette, distinguishing features)
and durable provenance (identity_id, version, decision proposal).

**Sources:**
- Schema: `packages/data-layer/src/monitor_data/schemas/visual_identity.py`
- Persistence + version transitions: `packages/data-layer/src/monitor_data/tools/mongodb_tools/visual_identities.py`
- Read assembly: `packages/agents/src/monitor_agents/image_context.py`
- Prompt builder: `packages/data-layer/src/monitor_data/llm/image_prompts.py`

## Fields

| Field | Purpose |
|-------|---------|
| `identity_id` | Unique id of this immutable version. |
| `character_id` | Card-level character; **null** for entity-anchored identities. |
| `entity_id` | Canonical Neo4j entity; requires `universe_id`. |
| `universe_id` | Canonical universe scope; **required** when `entity_id` is set. |
| `version` | Monotonic per anchor. N+1 replaces N; N is marked `superseded`. |
| `description` | Free-form prose (capped at 4,000 chars). |
| `species_or_type`, `apparent_age`, `build`, `hair`, `eyes`, `skin_or_surface`, `signature_attire`, `distinguishing_features`, `palette`, `style_hint` | Structured appearance cues used directly by the prompt builder. |
| `source` | `manual` / `card_import` / `canon` / `ai_extracted`. |
| `approved_reference_asset_ids` | Approved generated assets to forward as references. |
| `status` | `draft` → `approved` → `superseded`. |
| `decision_proposal_id` | The `ProposedChange` that approved or rejected this version. |

## Three anchor shapes

A `VisualIdentity` requires **exactly one** anchor:

| Shape | Fields set | Used when |
|-------|------------|-----------|
| **card default** | `character_id` only | The card's own appearance — no canonical anchor; carries across universes. |
| **incarnation** | `character_id` + `universe_id` (+ optional `entity_id`) | Per-universe character incarnation; isolated by `(character_id, universe_id)`. |
| **canonical entity** | `entity_id` + `universe_id` | The shared canon-driven identity for a Neo4j entity across characters. |

## Precedence

When the prompt builder resolves which identity to use for a subject, it
walks the anchors in this order and keeps the highest-precedence match:

```text
canonical entity   (entity_id + universe_id)   >   highest
approved incarnation (character_id + universe_id)        |
card default       (character_id only)                   |
card description / personality fallback           lowest
```

Concretely:

1. **Canonical entity** — the entity-anchored `VisualIdentity` from
   `mongodb_get_visual_identity(entity_id=…, universe_id=…, status="approved")`.
2. **Approved incarnation** — the incarnation-anchored approved identity,
   keyed by `(character_id, universe_id)`.
3. **Card default** — the identity carrying only `character_id` (no
   universe scope).
4. **Card fallback** — the character card's own `description` /
   `personality` fields, when no identity exists at any tier.

Conflicts keep the higher-precedence value and append a human-readable
warning naming the field and the ignored source. Rejected and draft
identities never appear in prompt text; only `status == "approved"` is
returned to the prompt builder.

## Incarnation isolation

Identities are scoped, not global. A card default exists once per
character and travels across universes; an incarnation belongs to one
universe; a canonical entity belongs to the entity's universe.

```python
# card default:      character_id="c1", universe_id=None,  entity_id=None
# incarnation:       character_id="c1", universe_id=u1,   entity_id=None
# canonical entity:  character_id=None,  universe_id=u1,   entity_id=e1
```

- A Marvel-style "Wolverine in the 616 universe" incarnation does not
  leak into the Ultimate universe incarnation.
- A card default carries across incarnations but is overridden by any
  higher-precedence identity in the active `(entity_id, universe_id)` or
  `(character_id, universe_id)` scope.
- Listing via `GET /api/image/visual-identities?character_id=…` returns
  every anchor lineage (card + incarnations); load editors with
  `status="approved"` and fall back to `status="draft"` when no
  approved version exists yet.

## CanonKeeper boundary

This is the rule that keeps the data layer consistent:

- **Identity property changes** (a new structured appearance version)
  for an entity-anchored identity enter the existing
  `mongodb_create_proposed_change(change_type="entity", ...)` flow
  with provenance pointing to the new `identity_id` and version.
  **CanonKeeper is the only agent that commits them to Neo4j** —
  the commit branch stores the compact identity verbatim under
  `properties["visual_identity"]` of the canonical entity.
- **Generated asset records** stay in MongoDB (with the binary in
  MinIO). Approval, rejection, and reference promotion are Mongo
  operations and never touch Neo4j. The only Neo4j writer is
  CanonKeeper, called for the identity change; the asset itself is
  out of scope for the canonical graph.

The decision-proposal reference is persisted on the identity
(`decision_proposal_id`) so the proposal → identity version
relationship is durable both ways. The acceptance path marks the exact
identity version `approved` with the proposal id; rejection keeps the
version `draft` and stores the decision reference so a future proposal
can re-evaluate it.

## Versioning

Each immutable version has a unique `identity_id`; replacing version N
creates a fresh record at N+1 and marks N `superseded`. The status
machine is strict:

```text
draft  -> approved
approved -> superseded
```

`mongodb_update_visual_identity_status(identity_id, status,
decision_proposal_id)` performs the in-place transition; same-status
calls are allowed so rejections can record provenance without
versioning up.

Optimistic locking: `VisualIdentityUpdate.identity_id` +
`expected_version` identify the version being replaced. Mismatches
return a typed `VisualIdentityConflictError` (mapped to HTTP 409 by
the router). Superseded targets are also rejected.

## See Also

- [Generated Assets — asset lifecycle](../3_loops_and_systems/image_generation.md)
- [Entity Types](./entity_types.md) — Archetype vs Instance.
- [Fact Canon Levels](./fact_canon_levels.md) — truth-grading; visual identity `decision_proposal_id` references a CanonKeeper proposal.
- [Ontology Index](./_index.md)
