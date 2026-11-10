# Phase 6 brief: safe for other people's accounts

> Read [README.md](README.md) first; its "Brief every agent gets" section applies here.

**Goal.** A second person can be given an account without being able to read or change the
first person's worlds, spend their model budget without limit, or read stored provider keys.
Required before inviting anyone; not required for solo play.

**Context.** Auth landed on master on 2026-11-09: accounts, sessions, API tokens, Google
OAuth, CSRF, an admin role, and a Postgres ownership registry enforced by
`resource_route_guard` and `_SCOPE_RESOLVERS` in `monitor_ui/ownership.py`.
`MONITOR_AUTH_DISABLED` gives a local admin. What the review found open:

- Ownership is enforced at the HTTP layer only. Agents and data-layer tools take ids and do
  not check an owner, so any route that forgets the guard leaks.
- Nine routers had no router-level auth dependency. Phase 1 task 8 adds a test that lists
  them; start from its output.
- `ensure_conversatory_universe` (`routers/character_conversation.py`) finds or creates one
  hidden universe by name and caches its id in a module global. Every user's standalone
  characters live in it.
- No per-user limit on model calls was found. Rate limits exist for login and signup only.
- `llm_providers.api_key` is a plain `TEXT` column in Postgres; no encryption was found.
- In-process caches (`_SESSIONS`, `_SCENE_LOOPS`, `_STORY_STATES`) are keyed by session or
  story id. Check that none can be reached with another user's id.

Verify each of these against current master before fixing it.

**Depends on.** Phase 1. Run after Phases 2, 3 and 4 have merged, or rebase on them: this
phase edits many routers.

**Needs a person.** The key-encryption scheme and where the master key lives; default quota
numbers; whether providers are per-user or admin-owned and shared.

**You own.** `packages/ui/backend/src/monitor_ui/ownership.py`, `auth.py`, `main.py`,
`routers/admin.py`, `routers/llm_mgmt.py`, router-level dependencies on every router,
`ensure_conversatory_universe`; `packages/data-layer/src/monitor_data/db/postgres.py`
(providers, ownership, a new usage table); `docs/architecture/MULTI_TENANCY_PLAN.md`.

**Do not touch.** Loop and agent logic. The Conversatory turn logic (Phase 7).

## Tasks

1. **Close the route gaps.** Every router gets a router-level auth dependency; public routes
   go in the explicit allowlist from Phase 1 task 8. Every route taking a resource id resolves
   ownership through `_SCOPE_RESOLVERS`.
2. **Cross-tenant test suite.** Two users, A and B. For every resource kind (universe, story,
   scene, session, character, persona, pack, ingest job, note, image, template, provider,
   API token), B's read, list, update and delete of A's resource return 404 or 403 and A's
   data is unchanged. Generate cases from the route table so new routes are covered.
3. **Per-user Conversatory universe.** One hidden universe per user, found through the
   ownership registry, not by name and not cached in a module global. Migrate existing
   standalone characters to their owner's universe.
4. **Search and retrieval.** Confirm Qdrant queries and Neo4j reads filter by a universe the
   caller owns. `/api/search`, `/api/graph` and the OpenAI-compatible endpoint are the ones to
   check first.
5. **Usage and quota.** Record tokens and calls per user per day. Enforce a configurable daily
   cap with a clear error to the client. Admin can view and change it.
6. **Provider keys.** Encrypt `api_key` at rest with a key from the environment. Never return
   a key from the API after creation (show the last 4 characters). Migrate existing rows.
   Confirm keys do not appear in logs.
7. **Process caches.** Key every in-process cache by user as well as resource, or check
   ownership before the cache is read.
8. **Defense in depth.** For the write tools the UI calls most (story, scene, character,
   memory), pass the owner through and assert it in the agent layer, so a missed guard fails
   closed.
9. **Docs.** Rewrite `MULTI_TENANCY_PLAN.md` as what is implemented, what is enforced where,
   and what remains.

## Out of scope

Organizations and shared worlds. Billing. Multiplayer in one scene. Row-level security in the
databases.

## Done when

- The cross-tenant suite passes and fails if any route's guard is removed.
- Two users each create a standalone character; neither can list, read or chat with the
  other's.
- A user at their daily cap gets a 429 with a readable message; other users are unaffected.
- `SELECT api_key FROM llm_providers` returns no plaintext key, and providers still work.
- The route-coverage test from Phase 1 shows zero unguarded routes outside the allowlist.
