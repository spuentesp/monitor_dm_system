# Phase 0 brief: a local stack that can run a turn

> Read [README.md](README.md) first; its "Brief every agent gets" section applies here.

**Goal.** On the owner's machine, one command brings up every service, every agent has a
model, and a fresh checkout can play one scene end to end. Every later phase's "done when"
check depends on this.

**Context.** Checked on 2026-11-09. Docker runs MongoDB, Postgres, Qdrant, Neo4j and Redis.
MinIO, GLiNER, the UI backend and the UI frontend are not running. Postgres holds 7
`llm_providers`, 0 `model_pairs` and 0 `llm_node_assignments`, so the retrieval boot gate
(`PairRegistry.validate_active_pair`) has no active pair and no agent node has an assigned
model. MongoDB `monitor` holds only seed data (game systems, tone profiles, tag definitions):
no packs, universes or sessions. The main checkout's `master` is 18 commits behind origin.

**Needs a person.** Provider API keys, and which provider to use for each tier. Ask; never
print, log or commit a key.

**You own.** `scripts/seed_*.py`, `scripts/sync_pair_from_defaults.py`, `scripts/doctor.sh`,
`dev.sh`, `Makefile` infra targets, `infra/docker-compose*.yml` (coordinate the MinIO image
change with Phase 1 task 2), `env.example`, and a new `docs/SETUP_LOCAL.md`.

**Do not touch.** Application code under `packages/*/src`. If setup needs a code fix, report
it instead.

## Tasks

1. **Bring the checkout up to date.** Fast-forward local `master` to `origin/master`. Do not
   discard untracked files.
2. **Start every service.** `make infra-up` or `dev.sh` must start MinIO and GLiNER too, or the
   stack must be configured not to need them (`STORAGE_BACKEND=folder`). Record which.
3. **Providers and tiers.** With the owner's choice, make sure a working provider exists for
   LIGHT, STANDARD, HEAVY and EMBEDDING. Verify each with `scripts/test_llm_connectivity.py` or
   `POST /api/llm/providers/{id}/test`.
4. **Active model pair.** Run `scripts/seed_model_pair.py` (or `sync_pair_from_defaults.py`)
   so `model_pairs` has one `status='active'` row matching the live providers. Confirm the
   embedding dimension matches the Qdrant collections; reindex with
   `scripts/reindex_embeddings.py` if not.
5. **Node assignments.** Decide whether an empty `llm_node_assignments` is intended (tier
   defaults apply) or a gap. If nodes need explicit rows, seed them from a checked-in script.
6. **Seed a world.** Run `scripts/seed_world_quick.py` or Quick World in the UI so one universe
   exists, then play three turns through the UI.
7. **One-command check.** Extend `scripts/doctor.sh` to fail on: no active pair, a tier with
   no provider, an unreachable store, a dimension mismatch. Its output is the first thing every
   other phase runs.
8. **Write it down.** `docs/SETUP_LOCAL.md`: from clone to first turn, in order, with the
   commands that were actually run.

## Out of scope

Production deployment. CI changes (Phase 1). Choosing models for quality.

## Done when

- `scripts/doctor.sh` exits 0 on the owner's machine.
- A person following `docs/SETUP_LOCAL.md` on a clean clone reaches a narrated turn.
- `model_pairs` has an active row; every tier resolves to a provider that answers.
- The three-turn transcript is attached to the report.
