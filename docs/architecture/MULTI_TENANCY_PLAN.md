# Multi-Tenancy Plan (Phase 1 of Multi-User / Multiplayer)

> **Status:** proposed (2026-07-31). Findings verified by direct code reading
> (grep for call sites, not just schema inspection) — see "Corrections to
> initial assumptions" below. Not yet implemented.
>
> This is **phase 1 only**: give each human user their own private
> campaigns. Real-time multiplayer (multiple humans + one LLM GM in a shared
> scene) is a separate, larger effort and explicitly out of scope here — see
> "Phase 2 (multiplayer) — not built here" at the bottom for what would be
> needed and why it's deferred.

## Context

The question driving this doc: can MONITOR become multi-user (each account
with private workspaces/campaigns) and, eventually, multiplayer? Three
codebase passes found no hard architectural blocker for either, but very
different amounts of existing scaffolding:

- **Multi-tenancy** has a real seam to build on: `Universe → Story →
  PlaySession → Scene` is already ID-scoped throughout Neo4j/Mongo, and
  Postgres already has `worlds` / `world_db_bindings` tables that *look*
  like per-tenant plumbing. But there is **zero** User/Account/auth concept
  anywhere in the repo, and (verified below) that Postgres plumbing is
  currently **dead code** — nothing populates or reads it at runtime.
- **Multiplayer** is a separate, larger effort: the GM ReAct loop and
  `SceneState` take exactly one `user_input`/`actor_id` per turn with no
  `speaker_id` concept, and web-backend session state is an unlocked,
  process-global in-memory dict. Deliberately out of scope for this plan —
  this doc only builds phase 1, while leaving explicit hooks (an empty
  `world_collaborators` stub table, untouched WebSocket fanout) so phase 2
  doesn't require re-migrating the same rows.

This plan covers phase 1: give each user their own private campaigns in the
web backend (`packages/ui/backend`), plus a public character-card/template
gallery (character.ai/RisuAI-style) per product decision — campaigns stay
strictly private, but character templates can be published and personally
imported by other users.

## Decisions made

- **D1 — Auth model: full email+password self-serve signup** (not
  admin-provisioned/invite-only). Signup + login + logout, argon2-hashed
  passwords, server-side sessions. No email verification flow in phase 1
  (the `users.email` column supports adding it later without a schema
  change).
- **D2 — Isolation model: strict per-user world isolation, PLUS a public
  template/character-card gallery.** Worlds/campaigns are never shared in
  phase 1. `EntityTemplate` (the existing NPC-blueprint/character-card
  concept) gains a `visibility` (`private` default | `public`) field and
  becomes usable independent of a single `universe_id` (currently
  `universe_id` is required on every template — becomes optional, so a
  template can be a personal/library card not yet attached to a world). A
  new read-only public gallery endpoint lists public templates across all
  owners; an import action clones a public template into the requesting
  user's own library or a target universe they own.
- **D3 — Logical, not physical, multi-tenancy.** Add `owner_id`
  columns/filters; do NOT wire the dormant `world_db_bindings` table into
  `db/neo4j.py`/`db/mongodb.py`/`db/qdrant.py` to route to per-tenant
  physical databases. That's a much larger, separate effort and isn't
  needed at hobby/small-team scale.
- **D4 — Ownership lives on Postgres `worlds.owner_id` only**, not
  duplicated onto the Neo4j `Universe` node. `Story`/`PlaySession`/`Scene`
  inherit ownership transitively via `universe_id` → `worlds.owner_id`.
- **D5 — Add `MONITOR_AUTH_DISABLED` dev-mode flag**, default **off**. When
  explicitly set, every request auto-resolves to a well-known local user, so
  existing solo self-hosted `docker compose`/`dev.sh` workflows can keep
  running with zero login friction if the operator opts in. Defaults off so
  a publicly exposed instance isn't accidentally wide open.

## Corrections to initial assumptions (verified by direct code reading)

These change what actually needs to be built:

1. **`world_db_bindings` and `active_world` are schema-only, unwired dead
   code.** Grepped the whole repo: `active_world_get`, `active_world_set`,
   and `world_full_get` (`packages/data-layer/src/monitor_data/db/postgres.py:1028,1049,1066`)
   have **zero callers** outside `postgres.py` itself and its own unit test.
   No router or agent ever reads `world_db_bindings` to route a request to
   a per-tenant database. Treat "per-tenant physical partitioning" as a
   future scaling seam, not a phase-1 dependency — don't "migrate away"
   from the singleton, just never wire it into new code.
2. **The `worlds` Postgres table itself is never populated at runtime.**
   `world_upsert` (`postgres.py:954`) is the only method that writes a
   `worlds` row, and it has **zero callers anywhere** — confirmed in both
   `packages/ui/backend/.../routers/universes.py` (`create_universe`) and
   `packages/cli/src/monitor_cli/commands/universe.py`. This is more
   significant than "add an owner_id column": **the first thing phase 1
   must do is wire `world_upsert` into both universe-creation paths for the
   first time.** The backfill script (Phase 7 below) must *create* missing
   `worlds` rows for every existing Neo4j `Universe`, not just patch
   `owner_id` on rows that don't yet exist.
3. `worlds_list()` (`postgres.py:938`) has no owner filter today — needs an
   `owner_id` parameter.
4. Chat session persistence bottoms out in
   `packages/ui/backend/src/monitor_ui/routers/chat_persistence.py` (Mongo
   + optional Redis cache) — this is the concrete file needing an
   `owner_id` field, in addition to the in-memory `_SESSIONS`/`_MESSAGES`
   dicts in `chat.py`.
5. The Next.js frontend has zero auth scaffolding (no next-auth/clerk/
   supabase); the proxy at
   `packages/ui/frontend/src/app/api/[...path]/route.ts` forwards all
   headers/cookies verbatim — a strong argument for httponly cookie
   sessions (browser + proxy handle it for free) over bearer tokens the
   frontend would have to manage.
6. CLI `monitor play`/`monitor playtest` never touch the FastAPI backend or
   any auth layer — unaffected by web auth, except it needs to stamp the
   well-known local-user id as `owner_id` when it creates worlds, so
   CLI-created and web-created campaigns resolve to the same account.
7. `AUTHORITY_MATRIX` in
   `packages/data-layer/src/monitor_data/middleware/auth.py` is unrelated —
   it governs which internal agent may call which MCP write tool, not
   end-user identity. No changes needed there.

## Target data model

### New Postgres tables (`packages/data-layer/src/monitor_data/db/postgres.py`)

```sql
CREATE TABLE IF NOT EXISTS users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           TEXT UNIQUE NOT NULL,
    username        TEXT UNIQUE NOT NULL,
    password_hash   TEXT NOT NULL,
    display_name    TEXT NOT NULL DEFAULT '',
    is_admin        BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sessions (        -- server-side auth sessions
    id              TEXT PRIMARY KEY,        -- opaque, cryptographically random
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at      TIMESTAMPTZ NOT NULL,
    last_seen_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions (user_id);

-- Stub only, unused in phase 1 — keeps the door open for phase-2 sharing.
CREATE TABLE IF NOT EXISTS world_collaborators (
    world_id        TEXT NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role            TEXT NOT NULL DEFAULT 'viewer',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (world_id, user_id)
);
```

### Modified existing tables (idempotent, following the existing
`ADD COLUMN IF NOT EXISTS` migration-block convention at the bottom of
`postgres.py`)

```sql
ALTER TABLE worlds
    ADD COLUMN IF NOT EXISTS owner_id UUID REFERENCES users(id);
-- nullable at first; backfill (Phase 7) sets it for all pre-existing rows
-- (creating rows via world_upsert where none exist yet — see Correction #2),
-- then a follow-up migration can make it NOT NULL.
```

`active_world` table: leave in place, untouched, unreferenced by any new
code (Correction #1). Schedule its removal as later cleanup once confirmed
fully dead.

### `EntityTemplate` changes for the public gallery (Decision D2)

`packages/data-layer/src/monitor_data/schemas/entity_templates.py`:
- `universe_id: UUID` → `universe_id: UUID | None` on create/response/filter
  (a template can now exist as a personal/library card not yet attached to
  any world).
- Add `owner_id: UUID` (required) and
  `visibility: Literal["private", "public"] = "private"`.
- `EntityTemplateFilter` gains `visibility` and `owner_id` filters so the
  gallery query (`visibility="public"`) and "my templates" query
  (`owner_id=current_user.id`) are both simple filtered lists.

### Pydantic schemas (new file, layer 1)

`packages/data-layer/src/monitor_data/schemas/users.py` — `UserCreate`,
`UserResponse` (never exposes `password_hash`), `SessionResponse`. Follow
the existing module-docstring/LAYER/IMPORTS-FROM header convention seen in
`schemas/universe.py`.

## Phased build order

### Phase 0 — User/session foundation (data-layer, no behavior change yet)
- `postgres.py`: add `users`, `sessions`, `world_collaborators` DDL;
  `owner_id` column on `worlds`; `PostgresClient` methods: `user_create`,
  `user_get_by_id`, `user_get_by_email`, `user_get_by_username`,
  `session_create`, `session_get`, `session_delete`, `session_touch`;
  extend `worlds_list(owner_id: str | None = None)`.
- `schemas/users.py` (new).
- `tests/test_db/test_postgres.py` — unit tests for every new method.
- New use case `SYS-13` — "Account creation & session lifecycle."

### Phase 1 — Auth dependency + password hashing (UI backend)
- `packages/ui/backend/pyproject.toml` — add `passlib[argon2]` (nothing
  password-related exists yet).
- `packages/ui/backend/src/monitor_ui/auth.py` (new) — `hash_password`,
  `verify_password`, `create_session_for_user`, FastAPI dependency
  `get_current_user(request) -> UserResponse` (reads session cookie, looks
  up `sessions` row, checks `expires_at`, loads `users` row, 401 if
  absent/expired) and `get_optional_user`. Respect `MONITOR_AUTH_DISABLED`
  (Decision D5): when set, auto-resolve to the well-known local user and
  log a loud startup warning.
- `packages/ui/backend/src/monitor_ui/routers/auth.py` (new) —
  `POST /api/auth/signup`, `POST /api/auth/login`, `POST /api/auth/logout`,
  `GET /api/auth/me`. Sets/clears an httponly, `SameSite=Lax` session
  cookie.
- `main.py` — register the auth router; verify `cors_origins_list` isn't
  `["*"]` in `config.py` (cookies require an explicit origin).
- `data-layer/config.py` / `env.example` — add `AUTH_SESSION_TTL_SECONDS`,
  `MONITOR_AUTH_DISABLED`.
- Use case `SYS-14` — "Signup / login / logout."

### Phase 2 — Wire world registration + owner_id enforcement
- **First**, wire `world_upsert` into `create_universe`
  (`packages/ui/backend/src/monitor_ui/routers/universes.py`) and into the
  CLI's universe creation (`packages/cli/src/monitor_cli/commands/universe.py`)
  — today neither path writes a `worlds` row at all (Correction #2). Stamp
  `owner_id = current_user.id` on creation.
- `universes.py` — every handler gains
  `current_user: UserResponse = Depends(get_current_user)`; `list_universes`
  filters via `worlds_list(owner_id=current_user.id)`; mutating/get
  endpoints check `worlds.owner_id == current_user.id`, else `404` (not
  `403`, to avoid leaking existence of other users' worlds).
- New shared helper `packages/ui/backend/src/monitor_ui/ownership.py` —
  `assert_owns_universe`, `assert_owns_story`, `assert_owns_session`, etc.,
  walking `story.universe_id`/`play_session.universe_id` →
  `worlds.owner_id` (Decision D4). Apply via `Depends` across `stories.py`,
  `play_sessions.py`, and the ~25 remaining routers that take a
  `universe_id`/`story_id`/`session_id` (`entities.py`, `graph.py`,
  `search.py`, `gm_tools.py`, `gm_notes.py`, `lorebook.py`,
  `canon_review.py`, `parties.py`, `change_log.py`, `architect.py`,
  `forge.py`, `image_gen.py`, `ingest.py`, `random_tables.py`, `tone.py`,
  `prompt_collections.py`). This is the bulk of the mechanical work — land
  it as several smaller PRs, one logical group of routers at a time.
- New use case `SYS-15` — "Cross-tenant access is rejected."

### Phase 2b — Public template/character-card gallery (Decision D2)
- `templates.py` router — `create_template`/`update_template` stamp
  `owner_id = current_user.id`; add `POST /api/templates/{id}/publish` and
  `/unpublish` (owner-only, flips `visibility`); add
  `GET /api/templates/public` (no ownership filter, `visibility="public"`
  only); add `POST /api/templates/{id}/import` — clones a public template
  into the current user's own library (new `owner_id`, `universe_id=None`
  unless a target universe they own is specified, fresh template id).
- `list_templates`/`get_template` for non-public templates gain the same
  ownership check as universes.
- New use case `SYS-17` — "Public template gallery & personal import."

### Phase 3 — Retire the `active_world` singleton pattern
- It's already unwired (Correction #1) — this phase is about not
  reintroducing it. Add a note to `AGENTS.md` "Common Mistakes": never
  resolve "the current world" from a process-global; always resolve
  `universe_id` explicitly per request, scoped to `current_user`.
- Verify frontend world/forge pages already pass an explicit `universe_id`
  through routing rather than assuming one implicit active world (check
  `packages/ui/frontend/src/app/forge/worlds/` and
  `packages/ui/frontend/src/components/forge/worlds/`) — likely already
  true since nothing calls `active_world_get` today.

### Phase 4 — Chat session ownership
- `chat_persistence.py` — stamp `owner_id` on session documents at
  creation time; `db_load_sessions` accepts and applies an `owner_id`
  filter to both the Mongo query and the Redis-cached
  `chat_sessions:index` list.
- `chat.py` — every `session_id`-bearing endpoint gains
  `Depends(get_current_user)` + an ownership check against the loaded
  session's `owner_id` before touching `_SESSIONS`/`_MESSAGES` or Mongo.
- `chat_ws.py` — WebSocket handshake must authenticate before subscribing:
  read the session cookie via `websocket.cookies`, resolve the user the
  same way `get_current_user` does, `websocket.close(code=4401)` if
  unauthorized or not the session owner, before adding to
  `_WS_SUBSCRIBERS`. No locking/turn-taking work here — that's explicitly
  phase-2 multiplayer, out of scope.
- New use case `SYS-16` — "Chat sessions are private to their owner."

### Phase 5 — `user_preferences` gains `user_id`
- PK shape change (`key` → `(user_id, key)`) — write as its own versioned
  migration block: add `user_id` nullable, backfill existing global rows
  to the well-known local-user id, then add the composite constraint.
  `preferences_get(user_id, key)`/`preferences_set(user_id, key, value)`
  replace the global-keyed versions.
- Grep and update whichever router currently reads/writes
  `user_preferences` to pass `current_user.id`.
- Amend existing `SYS-6` ("User Preferences") acceptance criteria to
  require per-user scoping (same feature gaining a dimension, not a new
  use case).

### Phase 6 — Frontend auth UI
- `packages/ui/frontend/src/app/login/page.tsx` and `.../signup/page.tsx`
  (new) — username/email/password forms posting to `/api/auth/login` /
  `/api/auth/signup` (proxied automatically; cookie set by the browser).
- Auth-state guard (e.g. `packages/ui/frontend/src/hooks/useCurrentUser.ts`
  using the existing `@tanstack/react-query` dependency) — redirect to
  `/login` on 401 from `GET /api/auth/me`; show current user + logout.
- Update world-listing pages (`forge/worlds/...`) to "my worlds" framing
  now that the list is user-scoped; add a public template gallery
  page/tab that calls `GET /api/templates/public` with an "import"
  button.

### Phase 7 — CLI / local-dev interop + backfill
- CLI universe creation stamps `owner_id` via the well-known local user
  (created if absent).
- One-off idempotent script `scripts/backfill_world_owners.py`: creates
  the well-known local user if absent; for every Neo4j `Universe` that has
  no corresponding `worlds` row, calls `world_upsert` to create one
  (Correction #2 — this is new, not just an `owner_id` patch); sets
  `owner_id` to the local user for every `worlds` row where it's still
  `NULL`. Run once during rollout; document in the PR description and
  `docs/5_infrastructure/`.

## Migration / backward-compatibility sequencing

1. All new tables/columns use `IF NOT EXISTS` — safe against a live dev DB.
2. Sequence explicitly to avoid a lockout window: **land Phase 0/1 (schema
   + auth, inert) → run the Phase 7 backfill script → land Phase 2
   (enforcement)**. Never let ownership checks run against `worlds` rows
   that don't exist yet or have `NULL owner_id`.
3. `MONITOR_AUTH_DISABLED=1` lets an existing solo self-hosted instance
   keep working with zero UI change immediately after upgrade. Default
   off; document prominently in `env.example`.
4. CLI solo-play is untouched by auth itself — its only change is
   stamping `owner_id` on creation, invisible to existing usage.
5. `active_world` table stays in place, unreferenced, rather than being
   dropped — avoids a destructive migration for a table that's already
   dead code; schedule removal as later cleanup once confirmed safe.

## Testing plan (per `AGENTS.md` / `docs/USE_CASES.md` conventions)

- New use cases go under the System epic
  (`docs/use-cases/epic-11-system-SYS/` — account/auth/session concerns,
  not the IDENTITY epic which covers in-fiction personas): `SYS-13`
  (account/session lifecycle), `SYS-14` (signup/login/logout), `SYS-15`
  (cross-tenant rejection), `SYS-16` (chat session privacy), `SYS-17`
  (public template gallery). Each needs both a `SYS-N-specification.md`
  and `SYS-N.yml` following the exact shape of `SYS-6`/`SYS-7`/`SYS-8`.
  Confirm the next free ID number at implementation time.
- `SYS-6` (User Preferences) acceptance criteria amended for per-user
  scoping, not superseded by a new ID.
- Unit tests per new use case under `tests/unit/SYS-13/` etc., mirroring
  existing docstring/naming conventions (e.g. `tests/unit/P-18/`). Cover:
  password hashing round-trip, session create/expire/delete,
  `get_current_user` 401 paths, ownership-helper allow/deny paths,
  template visibility/import logic.
- Integration/e2e (`RUN_INTEGRATION=1`/`RUN_E2E=1`): the critical
  regression test creates two real users against Postgres, has each
  create a world, and asserts `GET /api/universes` for user A never
  returns user B's world id. A second e2e test publishes a template as
  user A and confirms user B can see it in `GET /api/templates/public`
  and successfully import a private copy, but cannot see user A's
  *private* templates.
- `scripts/require_tests_for_code_changes.py` already enforces tests
  alongside `packages/*/src` changes — no script changes needed, just
  make sure every PR includes its test files.
- Every commit/PR references a use-case ID per existing CI convention.

## Critical files for implementation

- `packages/data-layer/src/monitor_data/db/postgres.py`
- `packages/data-layer/src/monitor_data/schemas/users.py` (new)
- `packages/data-layer/src/monitor_data/schemas/entity_templates.py`
- `packages/ui/backend/src/monitor_ui/auth.py` (new)
- `packages/ui/backend/src/monitor_ui/ownership.py` (new)
- `packages/ui/backend/src/monitor_ui/routers/universes.py`
- `packages/ui/backend/src/monitor_ui/routers/templates.py`
- `packages/ui/backend/src/monitor_ui/routers/chat_persistence.py`
- `packages/ui/backend/src/monitor_ui/routers/chat.py`
- `packages/ui/backend/src/monitor_ui/routers/chat_ws.py`
- `packages/cli/src/monitor_cli/commands/universe.py`
- `scripts/backfill_world_owners.py` (new)

## Verification

- Run `packages/data-layer` unit tests
  (`pytest packages/data-layer/tests/test_db/test_postgres.py`) after
  Phase 0 against a real Postgres test instance (per repo convention, not
  mocked — see `docs/testing/REPLAYS.md` and existing `test_postgres.py`
  fixtures).
- After Phase 2, run the new two-user integration test end-to-end against
  real Mongo/Neo4j/Postgres — spin up two accounts via `/api/auth/signup`,
  create a world under each, confirm `GET /api/universes` isolation
  holds.
- After Phase 6, manually exercise the full flow in a browser: signup →
  create a world → confirm it doesn't appear for a second signed-up
  account → publish a template → confirm the second account can see and
  import it from the public gallery.
- Run `scripts/check_layer_dependencies.py` before committing, per
  AGENTS.md.

## Phase 2 (multiplayer) — not built here, but the seam this plan preserves

Findings from the same research pass, kept here so the eventual multiplayer
design starts from verified facts instead of re-deriving them:

- Transport is already multi-connection-ready: FastAPI + WebSockets with
  Redis pub/sub fanout (`chat_ws.py`) already let multiple connections
  subscribe to one session (`_WS_SUBSCRIBERS`, `publish_redis_event`/
  `_listen_for_events`). This plan's Phase 4 only adds an auth gate in
  front of it — fanout mechanics are untouched.
- What would need to change structurally for multiplayer:
  1. A `speaker_id`/`player_id` field on the turn/action contract
     (`GMAgent.decide()`, `SceneState`, the DSPy `_GMReActSignature`) — none
     of these currently distinguish whose input is whose.
  2. Real locking or an action queue around `SceneLoop.run()` / the
     in-memory `_SESSIONS`/`_MESSAGES` dicts, so concurrent submissions
     from different humans in one session don't race (today there is zero
     locking).
  3. `CombatLoop` already models multiple simultaneous PCs via
     `CombatantState.is_pc`/`initiative_order` — a useful precedent to
     extend, but it still resolves one submitted string per call against
     `current_combatant_id`, with no mapping from *which connected human*
     controls that combatant.
  4. Context assembly's per-character filtering (`entity_id` in
     `context_assembly/agent.py`) would need to become multi-actor aware
     so no single player's memories dominate retrieval.
- The `world_collaborators` stub table (added in this plan, Phase 0) and
  the `sessions` (auth) table are both designed to be naturally compatible
  with a future `play_session_participants` roster concept — no naming/
  shape collision anticipated.
