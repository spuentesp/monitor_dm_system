# Multi-Tenancy — Implementation Plan (Phase 1)

> **Status:** ready to implement (2026-11-07). Derived from
> `docs/architecture/MULTI_TENANCY_PLAN.md` (the design rationale and decisions
> D1–D5) — this is the *executable* plan: concrete tasks, file anchors, tests,
> and verification per phase. Every anchor below was re-checked against the
> current code, not inherited from the design doc.
>
> **Scope (phase 1 only):** give each human user their own private campaigns in
> the web backend, plus a public character-template gallery. Real-time
> multiplayer (several humans + one LLM GM in one scene) is **out of scope**;
> the plan only preserves the seam for it (an empty `world_collaborators`
> table, untouched WebSocket fanout).
>
> **Relationship to the product boundary (2026-11-07):** none of this touches
> the narrative/mechanical split — multi-tenancy is an ownership concern.
> Templates here are the portable character templates from G-6 (portable prose,
> no stats), not mechanical systems.

---

## 1. Verified current state (what must actually change)

| Claim in the design doc | Verified 2026-11-07 |
|---|---|
| No User/Account/auth concept anywhere | Confirmed — no `users`/`sessions`/`world_collaborators` tables in `postgres.py`, no auth router, no auth UI |
| `world_upsert` is dead code | Confirmed — `packages/data-layer/src/monitor_data/db/postgres.py:954`; the only caller anywhere is `packages/data-layer/tests/test_db/test_postgres.py:381` |
| `active_world_get`/`active_world_set`/`world_full_get` are dead code | Confirmed — `postgres.py:1028,1049,1066`; only called from their own tests |
| `world_db_bindings` / `active_world` are schema-only | Confirmed — nothing reads them at runtime |
| `user_preferences` is global-keyed | Confirmed — `postgres.py:284` `key TEXT PRIMARY KEY`; a per-user variant needs a `(user_id, key)` PK migration |
| Frontend has no auth scaffolding | Confirmed — the Next.js proxy at `src/app/api/[...path]/route.ts` forwards headers/cookies verbatim, so httponly cookie sessions work without frontend token plumbing |
| `AUTHORITY_MATRIX` governs agents, not users | Confirmed — `middleware/auth.py` maps MCP tools to *agent* types; no changes needed there |
| The G-6 template surface now exists | New since the design doc: `schemas/character_templates.py`, `tools/mongodb_tools/character_templates.py`, and the router at `/api/characters/templates` — the gallery work must build on these, not on `EntityTemplate` alone |

**Infra note for the first implementation pass:** the dev stack was recreated
2026-11-07 (mongodb, postgres, qdrant, neo4j, redis healthy; MinIO and
OpenSearch images could not be pulled). The database is **empty**, so the
backfill script (P7) has nothing to migrate on the dev box — it must still be
written and tested, because production data is not empty.

---

## 2. Decisions carried over (D1–D5, unchanged)

- **D1 — Self-serve email+password signup**, argon2-hashed, server-side
  sessions. No email verification in phase 1.
- **D2 — Strict per-user world isolation, PLUS a public template gallery.**
  Templates gain `visibility` (`private` default | `public`) and `owner_id`;
  a template may exist unattached to any world (`universe_id: UUID | None`).
- **D3 — Logical, not physical, multi-tenancy.** Add `owner_id`
  columns/filters. Do **not** wire the dormant `world_db_bindings` table into
  the DB clients to route to per-tenant physical databases.
- **D4 — Ownership lives on Postgres `worlds.owner_id` only.** Story /
  PlaySession / Scene inherit it transitively via `universe_id`.
- **D5 — `MONITOR_AUTH_DISABLED` dev flag, default OFF.** When set, requests
  auto-resolve to a well-known local user with a loud startup warning, so a
  solo self-hosted instance keeps working with zero login friction.

---

## 3. Phased build order

Effort is in solo-dev days. Each phase is a separate PR with its own tests and
the standard gates (`ruff check`, `ruff format --check`, `mypy`,
`check_layer_dependencies.py`, the touched package's test suite).

### P0 — User/session foundation (data-layer) · 2–3 days

**Files:**
- `packages/data-layer/src/monitor_data/db/postgres.py` — add the `users`,
  `sessions`, `world_collaborators` DDL; `ALTER TABLE worlds ADD COLUMN IF NOT
  EXISTS owner_id UUID REFERENCES users(id)`; `PostgresClient` methods
  `user_create`, `user_get_by_id`, `user_get_by_email`,
  `user_get_by_username`, `session_create`, `session_get`, `session_delete`,
  `session_touch`; `worlds_list(owner_id: str | None = None)`.
- `packages/data-layer/src/monitor_data/schemas/users.py` (new) —
  `UserCreate`, `UserResponse` (never exposes `password_hash`),
  `SessionResponse`.
- `packages/data-layer/tests/test_db/test_postgres.py` — a test per new
  method against the real test Postgres instance (repo convention, not
  mocked).

**Exit gate:** every new method has a passing test; `uv run pytest
packages/data-layer/tests/test_db/test_postgres.py -q` is green.

### P1 — Auth dependency + password hashing + endpoints (UI backend) · 2–3 days

**Files:**
- `packages/ui/backend/pyproject.toml` — add `passlib[argon2]`.
- `packages/ui/backend/src/monitor_ui/auth.py` (new) — `hash_password`,
  `verify_password`, `create_session_for_user`, and FastAPI dependencies
  `get_current_user` (401 on absent/expired session) and `get_optional_user`.
  Honour `MONITOR_AUTH_DISABLED` (D5).
- `packages/ui/backend/src/monitor_ui/routers/auth.py` (new) —
  `POST /api/auth/signup`, `POST /api/auth/login`, `POST /api/auth/logout`,
  `GET /api/auth/me`. httponly, `SameSite=Lax` session cookie.
- `packages/ui/backend/src/monitor_ui/main.py` — register the router; verify
  `cors_origins_list` is an explicit origin, not `["*"]` (cookies).
- `packages/data-layer/src/monitor_data/config.py` + `env.example` — add
  `AUTH_SESSION_TTL_SECONDS`, `MONITOR_AUTH_DISABLED`.

**Tests:** password round-trip; session create/expire/delete; 401 on missing
and expired cookie; `MONITOR_AUTH_DISABLED` resolves the local user with a
warning.

**Exit gate:** `uv run pytest packages/ui/backend/tests/test_auth*.py -q`
green; a real signup → login → me → logout round-trip against the running
backend.

### P2 — World registration + ownership enforcement (the bulk) · 5–8 days

**Split into 3 PRs so review stays small.**

1. **Wire world registration first** (Correction #2 from the design doc):
   `world_upsert` has never been called by production code — today no `worlds`
   row exists at all. Wire it into
   `packages/ui/backend/src/monitor_ui/routers/universes.py`
   (`create_universe`) and `packages/cli/src/monitor_cli/commands/universe.py`,
   stamping `owner_id = current_user.id` (the well-known local user on the CLI
   path).
2. **The ownership helper:** new
   `packages/ui/backend/src/monitor_ui/ownership.py` —
   `assert_owns_universe`, `assert_owns_story`, `assert_owns_session`, each
   walking `universe_id` → `worlds.owner_id` and returning **404** for
   non-owners (never 403 — don't leak that another user's world exists).
3. **Apply the helper across the routers in logical groups:** `universes.py`
   and `stories.py` first (the campaign surface), then `entities.py`,
   `graph.py`, `search.py`, then the Forge/GM surfaces (`gm_tools.py`,
   `gm_notes.py`, `canon_review.py`, `forge.py`, `ingest.py`, `lorebook.py`,
   `parties.py`, `change_log.py`, `architect.py`, `image_gen.py`,
   `random_tables.py`, `tone.py`, `prompt_collections.py`,
   `character_templates.py`).

**Tests:** an ownership-allow and ownership-deny case per router group;
`list_universes` filtered to the current user.

**Exit gate:** the two-user integration test — create a world as user A,
confirm it is invisible to user B — passes for the routers in that PR.

### P2b — Public template gallery · 2–3 days

**Files:**
- `packages/data-layer/src/monitor_data/schemas/character_templates.py` and
  `packages/data-layer/src/monitor_data/schemas/entity_templates.py` —
  `owner_id` (required on write), `visibility` (`private` | `public`),
  `universe_id` becomes optional on create/response/filter.
- `packages/data-layer/src/monitor_data/tools/mongodb_tools/character_templates.py`
  — carry the fields through create/convert/list; support `owner_id` and
  `visibility` filters.
- `packages/ui/backend/src/monitor_ui/routers/character_templates.py` —
  `POST /templates/{id}/publish` and `/unpublish` (owner-only),
  `GET /templates/public` (no ownership filter), `POST /templates/{id}/import`
  (clone into the current user's library, fresh id, `universe_id=None` unless
  the caller names a universe they own).

**Tests:** publish → visible in the public gallery for another user; private
templates never leak; import clones with a fresh id and the caller as owner.

**Note:** do this against the G-6 template schema, not `EntityTemplate` alone —
the G-6 surface is the one a GM actually uses for portable characters.

### P3 — Retire the `active_world` singleton pattern · 0.5 day

- Doc-only: add to `AGENTS.md` "Common Mistakes" — never resolve "the current
  world" from a process-global; always resolve `universe_id` explicitly per
  request, scoped to `current_user`.
- Verify the frontend world/forge pages pass an explicit `universe_id` through
  routing (they already do, since nothing calls `active_world_get`).
- Leave the table in place, unreferenced; schedule removal as later cleanup.

### P4 — Chat session ownership (incl. WebSocket) · 3–4 days

**Files:**
- `packages/ui/backend/src/monitor_ui/routers/chat_persistence.py` — stamp
  `owner_id` on session documents at creation; `db_load_sessions` gains an
  `owner_id` filter applied to both the Mongo query and the Redis-cached
  session index.
- `packages/ui/backend/src/monitor_ui/routers/chat.py` — every
  `session_id`-bearing endpoint gains `Depends(get_current_user)` plus the
  ownership check before touching `_SESSIONS`/`_MESSAGES` or Mongo.
- `packages/ui/backend/src/monitor_ui/routers/chat_ws.py` — the WebSocket
  handshake authenticates *before* subscribing: read the session cookie,
  resolve the user exactly as `get_current_user` does, and close with
  `websocket.close(code=4401)` for unauthorized or non-owner connections.
  Fanout itself is untouched — no locking/turn-taking here (that is phase-2
  multiplayer).

**Tests:** a session owned by A returns 404 for B over HTTP and over the WS
handshake; a session list only ever contains the caller's sessions.

### P5 — `user_preferences` gains `user_id` · 1–2 days

- Migration block in `postgres.py`: add a nullable `user_id`, backfill the
  existing global rows to the well-known local user, then make the PK
  `(user_id, key)`.
- `preferences_get(user_id, key)` / `preferences_set(user_id, key, value)`
  replace the global-keyed methods; update every caller to pass
  `current_user.id`.
- Amend `SYS-6` (User Preferences) acceptance criteria for per-user scoping —
  the same feature gaining a dimension, not a new use case.

### P6 — Frontend auth UI · 2–3 days

- `packages/ui/frontend/src/app/login/page.tsx` and `.../signup/page.tsx`
  (new) — forms posting to `/api/auth/login` / `/api/auth/signup` (the proxy
  forwards them; the cookie is set by the browser).
- `packages/ui/frontend/src/hooks/useCurrentUser.ts` (new) — `GET
  /api/auth/me` via React Query; redirect to `/login` on 401; show the current
  user + a logout action.
- Update the world-listing pages to "my worlds" framing, and add a public
  template gallery page/tab calling `GET /api/templates/public` with an
  import button.

**Tests:** the login form submits and lands on the session; a 401 redirects to
`/login`.

### P7 — CLI interop + backfill · 1 day

- CLI universe creation stamps `owner_id` via the well-known local user
  (created if absent).
- New `scripts/backfill_world_owners.py` (idempotent): create the well-known
  local user if absent; for every Neo4j `Universe` with no matching `worlds`
  row, call `world_upsert` to create one; set `owner_id` on every `worlds` row
  where it's still `NULL`. Document the run in
  `docs/5_infrastructure/`.

---

## 4. Rollout order — avoiding the lockout window

**This ordering is a hard requirement, not a preference:**

1. **P0 + P1 first (schema + auth, inert).** Nothing enforces ownership yet.
2. **Run P7's backfill** against the live DB. Every existing `Universe` must
   have a `worlds` row with a non-null `owner_id` before enforcement lands.
3. **Only then land P2 (enforcement)** — a check that runs against a missing
   or `NULL` row would lock every existing user out of their own campaigns.
4. `MONITOR_AUTH_DISABLED=1` lets an existing solo instance keep working
   immediately after upgrade, with zero UI change. Default off, and document
   it prominently in `env.example`.
5. The CLI solo-play path is unaffected by auth itself — its only change is
   stamping `owner_id` on creation.

---

## 5. Testing plan

- **Per phase:** unit tests for the new methods and endpoints (the files named
  in each phase above).
- **Integration (the acceptance test for P2):** two real users via
  `/api/auth/signup`; each creates a world; assert `GET /api/universes` for A
  never returns B's world id. Run with `RUN_INTEGRATION=1` against the real
  stack.
- **Gallery (P2b):** user A publishes a template; user B sees it in
  `GET /templates/public` and imports a private copy, but never sees A's
  private templates.
- **End-to-end (P4):** a session created by A is invisible to B over both HTTP
  and the WebSocket handshake.
- **Use cases:** new `SYS-13` (account/session lifecycle), `SYS-14`
  (signup/login/logout), `SYS-15` (cross-tenant rejection), `SYS-16` (chat
  session privacy), `SYS-17` (public template gallery) under
  `docs/use-cases/epic-11-system-SYS/` — confirm the next free ID at
  implementation time. Amend `SYS-6` for per-user preferences.
- **Conventions:** tests live in `tests/unit/SYS-*/` and the per-package test
  dirs. **Never** modify `tests/verification/**` or `tests/property/**`
  (sealed).

## 6. Verification commands (per PR)

```bash
uv run ruff check packages scripts
uv run mypy packages/*/src --cache-dir /tmp/mypy-cache
uv run python scripts/check_layer_dependencies.py
uv run pytest packages/data-layer/tests/test_db/test_postgres.py -q
uv run pytest packages/ui/backend/tests -q
# after P2b (the frontend gallery lands):
cd packages/ui/frontend && npx tsc --noEmit && npx vitest run
```

The full suite (`uv run pytest packages tests -q`) is the gate before the
final PR merges.

## 7. Risks and open decisions

- **The `worlds` table is empty in production, not just unowned.** P2's first
  step (wiring `world_upsert`) is therefore a prerequisite for *everything*
  else — without it, the ownership helper has nothing to check against. It is
  the single most important line of work in this plan.
- **404-vs-403** must be applied consistently, or the API leaks which worlds
  exist.
- **Cookie vs bearer** is settled by the proxy's verbatim forwarding: cookie.
  If a bearer-token API surface is ever needed for programmatic access, that
  is a separate decision (and a separate PR).
- **MinIO/OpenSearch could not be pulled** in the dev environment. The image
  and search surfaces are not part of this plan, but a browser pass of the
  gallery will not be possible until MinIO is available.
- **Multiplayer is explicitly out of scope** — the `world_collaborators` stub
  and the auth sessions table are shaped to support a later participant
  roster without another migration.

## 8. Effort and PR sequence

| # | PR | Days |
|---|---|---|
| 1 | P0 user/session foundation | 2–3 |
| 2 | P1 auth dependency + endpoints | 2–3 |
| 3 | P2.1 world registration (`world_upsert` wiring) | 1–2 |
| 4 | P2.2 ownership helper + universes/stories | 2–3 |
| 5 | P2.3 ownership across the remaining routers | 2–3 |
| 6 | P2b public template gallery | 2–3 |
| 7 | P3 active_world retirement note | 0.5 |
| 8 | P4 chat session + WebSocket ownership | 3–4 |
| 9 | P5 per-user preferences | 1–2 |
| 10 | P6 frontend auth UI + gallery page | 2–3 |
| 11 | P7 CLI interop + backfill script | 1 |

**Total: ~4–6 weeks solo.** P2b (the gallery) is independent of P2 and can be
scheduled earlier if the public gallery matters more than strict isolation.
