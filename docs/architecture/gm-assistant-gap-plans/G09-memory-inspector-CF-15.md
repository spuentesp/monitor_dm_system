# G09 — Per-character knowledge inspector (proposed CF-15)

> **Status:** implemented 2026-11-11 as **CF-15** (the knowledge audit tool,
> the `KnowledgeAuditAgent`, the audit/challenge routes, and the Knowledge
> tab in the lookups panel). Originally proposed 2026-11-11. Gap: the memory
> inspector was recorded as
> a future use case in `docs/USE_CASES.md` (two-tier hub spec) and never
> built. `/gm/lookup/party-knowledge` answers questions, but the GM cannot
> *audit* what the system believes each PC knows — the difference between
> asking and inspecting.

## Goal

A GM panel that lists, per PC (or per party), the facts/memories the system
attributes to them, each with source (scene, witnessed, proposal) and
confidence, with the ability to challenge ("this PC doesn't actually know
that") which stages a correction proposal for CF-8.

## Use case

Propose **CF-15 "Inspect Character Knowledge"** in
`docs/use-cases/epic-7-copilot-CF/CF-15/`; related: CF-6's
witnessed-facts filtering must share the same underlying query.

## Design

- **Layer 1:** read-only aggregation over existing stores —
  `neo4j_list_facts(witnessed_by=…)`, memories from Mongo with
  `importance`, scenes by participant; new tool
  `mongodb_tools/knowledge_audit.py` returning per-entity knowledge items
  with provenance. **No new writes to Neo4j.**
- **Layer 2:** `KnowledgeAuditAgent` (`monitor_agents/knowledge_audit.py`)
  — assembles the per-PC view (deterministic grouping) + optional DSPy
  module that flags *suspicious* attributions (facts with weak provenance
  or contradictions with the PC's witnessed scenes). Challenge action →
  `ProposedChange` (correct/retract fact) for CF-8.
- **Layer 3:** `GET /gm/knowledge/{character_id}` in `gm_tools.py`;
  `POST /gm/knowledge/{character_id}/challenge`; UI: "Knowledge" tab in the
  Lookups panel (`TableLookupsPanel.tsx`) or its own panel in `GM_PANELS`.

## Phases

1. Provenance query + tools + tests (facts with source scene/proposal,
   importance, witnessed_by).
2. Agent assembly + suspicion heuristics + fake-client tests.
3. Routes + authz + backend tests.
4. UI panel + vitest; challenge flow into CF-8.

## Acceptance

- GM opens a PC and sees every attributed fact with provenance; filtering
  by source/confidence works.
- "Challenge" stages a CF-8 proposal; accepting it corrects canon through
  CanonKeeper only.
- `party-knowledge` lookup and CF-6 handouts reuse the same witnessed-facts
  query (no divergent logic).
- Commits reference CF-15; tests green; layer check clean.

## Open decisions

- Suspicion heuristic vs. LLM judgment for flagging (v1: heuristic only).
- Party-level aggregated view (v1) vs. per-PC only.
