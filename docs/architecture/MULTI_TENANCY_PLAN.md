# Multi-Tenancy Implementation Plan

> **Status:** proposed; revised 2026-11-07 after a fresh code review. Not yet
> implemented.
>
> **Scope:** private per-user accounts, campaigns, characters, chats, uploaded
> content, and preferences, plus an authenticated public character-card
> gallery. Multiplayer and physical database partitioning are explicitly out of
> scope.

## 1. Goal and release contract

MONITOR currently has no end-user account or authentication model. This plan
adds logical multi-tenancy to the existing shared Postgres, Neo4j, MongoDB,
Qdrant, Redis, and MinIO deployments without splitting the CLI and web
architectures or changing CanonKeeper's authority.

The release is complete only when all of these invariants hold:

1. Every private runtime resource has exactly one resolved owner.
2. Every HTTP and WebSocket operation is authenticated, except explicitly
   public routes such as health, signup, and login.
3. List queries apply ownership before pagination and never return another
   user's IDs, metadata, counts, text, embeddings, images, or error details.
4. Get, update, delete, export, and action endpoints authorize the resource and
   every referenced parent/child resource. A foreign or missing private ID
   returns the same `404` response.
5. Ownership is enforced at the backend, not merely hidden by the frontend.
   Cache hits, background jobs, OpenAI-compatible clients, and WebSockets use
   the same rules as ordinary HTTP requests.
6. Existing installations are backfilled and verified before enforcement is
   enabled. Missing ownership fails closed rather than making a resource
   public or assigning it to the caller.
7. `MONITOR_AUTH_DISABLED` is an explicit local-development exception, never a
   production rollback or migration mechanism.

### Non-goals

- Multiple humans participating in one shared scene or turn queue.
- Organizations, invites, collaborator roles, or world sharing.
- Per-tenant Neo4j/MongoDB/Qdrant databases or collections.
- Anonymous browsing of the public gallery. In this phase, “public” means
  visible to other authenticated users.
- Email verification, self-service password reset, SSO, MFA, or account
  deletion. Signup still proves control of no email address; the UI must not
  claim otherwise.
- Publishing universes, knowledge packs, or `EntityTemplate` objects.

## 2. Verified current state and corrections to the earlier plan

These findings come from direct call-site and router inspection. They are
implementation constraints, not optional cleanup.

1. **Postgres world registration is currently dead plumbing.** `worlds_list`,
   `world_get`, and `world_upsert` are in
   `packages/data-layer/src/monitor_data/db/postgres.py`, but runtime universe
   creation does not register rows. `world_db_bindings` and `active_world` are
   also not used for request routing. The backfill must therefore create rows,
   not merely populate a new column.
2. **There are many world-creation paths, not two.** In addition to
   `routers/universes.py` and CLI `commands/universe.py`, worlds can be created
   by `commands/play.py`, WorldArchitect, Quick World, pack application,
   ingestion helpers, Forge, universe fork, and the standalone-character
   Conversatory. Wiring two routers would leave most new worlds ownerless.
3. **Multiverses need their own ownership registry.** An empty multiverse has
   no child world from which to derive an owner. Filtering only `worlds` would
   leak all multiverses and allow creation beneath another user's parent.
4. **The actual universe API paths are nested.** For example, the current list
   route is `GET /api/universes/universes`, as used by
   `packages/ui/frontend/src/lib/api.ts`, not `GET /api/universes`.
5. **`EntityTemplate` is not the standalone character-card model.** It is a
   world-scoped NPC generation blueprint with required `universe_id`, parent
   inheritance, random-table references, and instantiation behavior. Making it
   optionally global would expand the authorization problem and break response
   contracts. Standalone character cards already exist in the Mongo
   `characters` collection and are managed by `entities.py` and
   `character_storage.py`; they are the correct gallery resource.
6. **Standalone characters have sensitive attached state.** Lorebook entries,
   avatars, versions, Neo4j backing entities, NPC profiles, memories,
   conversations, and proposed changes all need an ownership decision. Public
   import must copy only deliberately published card content, never runtime
   state.
7. **The Conversatory is currently process-global.** `character_conversation.py`
   finds or creates one hidden universe named `Conversatory` and caches one ID.
   That cannot be shared by all users after isolation is enabled.
8. **Chat has both durable and shared-cache state.** `chat_persistence.py` uses
   Mongo plus Redis. Its global `chat_sessions:index` key is itself a leak if it
   is retained. Filtering only after reading that index is insufficient.
9. **WebSockets currently accept before loading or authorizing a session.** The
   handler in `chat.py` also accepts inbound turn-producing messages, so a
   connect-time-only check is not enough for expired or revoked sessions.
10. **Rootless data is broader than chat.** Sources, ingestion jobs, knowledge
    packs, standalone characters/conversations, user preferences, and some
    custom libraries cannot always derive ownership from a universe.
11. **Unscoped semantic search is a direct cross-tenant read.** `GET
    /api/search/search` makes `universe_id` optional and returns full Qdrant
    payloads. Post-filtering a small top-k result is both unsafe and incorrect.
12. **The OpenAI-compatible endpoint is a separate client surface.** RisuAI,
    SillyTavern, and LiteLLM cannot be assumed to use a browser session cookie.
    `/api/v1/chat/completions` needs per-user API tokens and the same character
    and conversation checks as the web routes.
13. **Background work needs explicit identity.** Ingest queue entries and
    workers outlive the request. They must persist `owner_id` at submission and
    use it when creating worlds or exposing job status; they must not read an
    ambient request user later.
14. **CLI layering matters.** `packages/cli` may import agents but not the data
    layer. CLI ownership/registration therefore belongs in a Layer 2 service,
    not a new `monitor_data.db.postgres` import in a command.
15. **The existing preference methods are named `pref_get`/`pref_set`, not
    `preferences_get`/`preferences_set`.** They have no runtime router callers
    today. Their table is still global-keyed and must be migrated before being
    exposed as per-user settings.
16. **Postgres unit tests are mocked, not real-database tests.** The existing
    `test_postgres.py` uses mocked asyncpg. Real Postgres belongs in a separate
    integration test; the verification section below distinguishes them.
17. **The current route surface is large.** There are roughly 294 route
    decorators across 32 backend router modules. An inventory and route-policy
    completeness test are required; a hand-picked list of “about 25 routers” is
    not a release gate.

## 3. Decisions

### D1 — Self-serve email/password signup, server sessions, and API tokens

- Support signup, login, logout, and `GET /api/auth/me`.
- Hash passwords with Argon2id using `argon2-cffi` directly, with library-
  recommended parameters and rehash-on-login when parameters change. Do not add
  the unmaintained compatibility stack merely for a single hash algorithm.
- Use opaque, cryptographically random browser session tokens. The cookie holds
  the raw token; Postgres stores only its SHA-256 hash.
- Set cookies with `HttpOnly`, `Secure` outside explicit local development,
  `SameSite=Lax`, `Path=/`, no `Domain`, and a bounded expiration. Rotate the
  token on login and privilege changes; logout deletes the server session.
- Add per-user, revocable API tokens for non-browser OpenAI-compatible clients.
  Display the raw token once and store only its hash plus a non-secret prefix.
- Add shared rate limiting to signup/login/token verification and costly LLM
  invocation. Key login limits by both normalized account and trusted client
  IP; only trust forwarded headers from configured proxies.

### D2 — Strict private tenancy plus a standalone character gallery

- Worlds, campaigns, chats, sources, packs, private characters, and user-
  authored libraries are private by default.
- Mongo `characters` documents gain `owner_id`, `visibility`, and publication
  metadata. Owners can publish/unpublish a card and other authenticated users
  can read or import the published snapshot.
- Publishing explicitly includes the card text (including `gm_notes` and
  `first_message`), embedded lorebook, and avatar. The publish UI must show
  this warning before confirmation.
- Import creates a fresh private card, fresh lorebook IDs, and copied avatar
  assets. It does not copy versions, backing entity IDs, NPC profiles,
  memories, conversations, proposals, universe links, counters, or ownership.
  Unpublishing or deleting the source does not revoke existing imports.
- `EntityTemplate.universe_id` remains required on create, response, and
  instantiate contracts. Entity templates remain private world resources;
  their inheritance and random-table references are not made public in this
  phase.

### D3 — Logical isolation, with canonical ownership in Postgres

Do not wire `world_db_bindings` into physical tenant routing. Keep shared
infrastructure and add owner-scoped queries and metadata.

Postgres is authoritative for ownership of Neo4j roots:

- `multiverses.owner_id` owns a Multiverse.
- `worlds.owner_id` owns a Universe.
- Story, PlaySession, Scene, Entity, Fact, and other world data inherit through
  their validated `universe_id` chain.

Rootless Mongo records carry their own `owner_id`. This is not duplication of
world ownership; it is the ownership record for resources that have no world.
Qdrant payloads may denormalize scope metadata for filtering, but that metadata
is never treated as proof that the caller owns the resource.

Do not add `owner_id` to every Neo4j node. Do not trust an owner supplied in a
create/update request body; the server derives it from the authenticated
principal.

### D4 — Deny by default and hide private existence

- No valid session/API token: `401` for private routes.
- Valid user but missing, unregistered, unbackfilled, or foreign private
  resource: `404` with one generic detail.
- Authenticated non-admin calling an operator-only route: `403`.
- Public character access is allowed only when the stored resource is currently
  `visibility="public"`; all mutations still require its owner.
- Never silently fall back to all records when an owner filter is absent,
  malformed, or empty. Internal administrative methods must have distinct,
  explicit names so a forgotten argument cannot become an unscoped web query.

### D5 — Explicit local identity for solo development

Reserve a fixed local user UUID, for example
`00000000-0000-4000-8000-000000000001`, and email
`local@monitor.invalid`.

When `MONITOR_AUTH_DISABLED=true`, web requests resolve to this user and CLI
creation uses the same identity. Startup emits a prominent warning. The flag
defaults to false and must not be set in committed production configuration.
Tests opt in through fixtures/dependency overrides rather than changing the
developer's real environment.

Backfilled solo data belongs to this local account, which is explicitly an
admin so auth-disabled solo mode retains access to operator settings. Its
initial password hash is random and unusable; an operator who later enables
auth must run the local password-setting command and must understand that this
password unlocks an admin account. The first public signup must never
automatically claim legacy data or become admin.

### D6 — No speculative multiplayer schema

Do not create an unused `world_collaborators` table. A future role and roster
model needs its own design and migration. This plan preserves compatibility by
keeping user IDs stable and by avoiding a singleton owner inside gameplay
state, but implements no sharing behavior.

## 4. Target data model

### 4.1 Versioned Postgres migrations

The current `postgres.py` schema string is suitable for additive development
DDL, but primary-key changes and ownership rollout need auditable, ordered
migrations. Add a `schema_migrations` table and transactional, numbered
migration functions. Each migration records version, checksum, and applied
time; application startup must report pending migrations rather than partially
applying a new schema on every connection.

Use shapes equivalent to the following; final names and types should match the
existing client's `TEXT` UUID convention for world references and `UUID` for
user references.

```sql
CREATE TABLE users (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email               TEXT NOT NULL,
    email_normalized    TEXT NOT NULL UNIQUE,
    username            TEXT NOT NULL,
    username_normalized TEXT NOT NULL UNIQUE,
    password_hash       TEXT NOT NULL,
    display_name        TEXT NOT NULL DEFAULT '',
    is_admin            BOOLEAN NOT NULL DEFAULT FALSE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE auth_sessions (
    token_hash       TEXT PRIMARY KEY,
    user_id          UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at       TIMESTAMPTZ NOT NULL,
    last_seen_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_auth_sessions_user ON auth_sessions(user_id);
CREATE INDEX idx_auth_sessions_expiry ON auth_sessions(expires_at);

CREATE TABLE api_tokens (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    token_prefix    TEXT NOT NULL,
    token_hash      TEXT NOT NULL UNIQUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at      TIMESTAMPTZ,
    last_used_at    TIMESTAMPTZ,
    revoked_at      TIMESTAMPTZ
);
CREATE INDEX idx_api_tokens_user ON api_tokens(user_id);

CREATE TABLE multiverses (
    id          TEXT PRIMARY KEY,
    owner_id    UUID REFERENCES users(id) ON DELETE RESTRICT,
    label       TEXT NOT NULL,
    active      BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_multiverses_owner ON multiverses(owner_id);

ALTER TABLE worlds
    ADD COLUMN owner_id UUID REFERENCES users(id) ON DELETE RESTRICT;
CREATE INDEX idx_worlds_owner ON worlds(owner_id);
```

`owner_id` starts nullable only to permit expansion and backfill. The final
migration makes both ownership columns `NOT NULL` after verification. Add
`worlds.multiverse_id TEXT` and a foreign key to `multiverses.id` if parent
validation is performed through Postgres; otherwise the ownership service must
validate the Neo4j parent on every creation/update. Prefer storing this parent
reference once in the registry and reconciling it during backfill.

Add `auth_sessions` cleanup and expired/revoked token tests. Raw tokens,
passwords, and password hashes must never appear in responses or logs.

For preferences, avoid an in-place primary-key rewrite on a live table. Create
`user_preferences_by_user (user_id, key, value, updated_at)` with primary key
`(user_id, key)`, copy legacy rows to the local user, switch `pref_get` and
`pref_set` to require `user_id`, and retain the old table read-only until a
later destructive-cleanup migration.

### 4.2 Pydantic contracts

Add `schemas/users.py` with the repository's layer header and separate models
for:

- `UserCreate`, normalized signup input, and password validation.
- `UserResponse`, excluding `password_hash` and all token data.
- `AuthSessionResponse`, containing expiry/user metadata, never the token hash.
- `ApiTokenCreate`, `ApiTokenCreatedResponse` (the only response containing the
  raw token), and `ApiTokenMetadataResponse`.
- Internal authenticated-principal and ownership-context types where useful.

Use bounded password and profile fields. Normalize email/username with a
single deterministic function before validation and lookup; preserve the
original email for display. Enforce a reasonable minimum password length and a
maximum request size. Database uniqueness handles signup races; translate
conflicts without leaking password material.

Do not put `owner_id` or `visibility` into general client create/update models
where a caller could mass-assign them. Use server-owned internal fields or
dedicated publish/import endpoints.

### 4.3 MongoDB, Qdrant, Redis, and MinIO

Add and index these fields, serializing UUIDs consistently as strings:

| Resource | New scope metadata | Required behavior |
|---|---|---|
| `characters` | `owner_id`, `visibility`, `published_at`, optional `imported_from_character_id` | Owner list/mutation; public read/import only for published cards |
| `conversations` | `owner_id`, `character_id` | Verify both IDs belong to caller and match the requested character |
| `chat_sessions` | `owner_id` | Every read/write/delete includes owner; creation derives world ownership too |
| `documents` / sources | `owner_id` | Owner-only source reads, exports, rescans, deletes, and snippet search |
| `ingestion_jobs` | `owner_id` | Captured at submission; owner-scoped list/get/cancel/delete |
| `knowledge_packs` | `owner_id` | Owner-scoped CRUD, clone/merge/slice/import/export/apply |
| Rootless custom libraries | `owner_id` where no universe exists | Separate user-authored records from built-in global records |
| `user_preferences` migration target | `user_id` | Composite user/key reads and writes |

Create compound indexes that match actual queries, including
`characters(owner_id, updated_at)`, `characters(visibility, published_at)`,
`chat_sessions(owner_id, updated_at)`, `ingestion_jobs(owner_id, updated_at)`,
and `conversations(owner_id, character_id, updated_at)`. Migration code must
handle duplicate/index failures explicitly rather than treating index creation
as best effort.

For Qdrant:

- Require a validated `universe_id` on all private vector searches. Make the
  currently optional universe on global search mandatory, or replace the route
  with the existing universe-scoped route.
- Validate ownership before constructing `VectorSearchRequest`; do not retrieve
  unscoped results and filter them in Python.
- Repair or quarantine legacy points without `universe_id`. They must not be
  returned from a global unscoped query.
- Source snippets that can exist without a universe need an owner-scoped
  payload/filter and a corresponding reindex/backfill. Keep this as query
  metadata only; authorize the source through Mongo first.
- Audit `custom` vector filters. Web callers must not be able to override or
  remove the server-added ownership predicate.

For Redis:

- Replace `chat_sessions:index` with versioned per-user keys such as
  `v2:chat_sessions:index:{owner_id}`.
- Populate an index only from an owner-scoped Mongo query. `db_save_session`
  updates only that owner's index.
- Require owner in `db_load_sessions`, session load/save/delete, and message
  load helpers. A cache miss or Redis failure falls back to the same scoped
  Mongo query, never an unscoped one.
- Session/message cache entries keyed only by session ID are usable only after
  an owner-scoped durable lookup. Namespacing them by owner as well is
  preferred for defense in depth.
- Do not log cached message bodies or publish ownership metadata unnecessarily
  to shared pub/sub channels.

For MinIO/images:

- Authorize avatar and generated-asset downloads through their owning character
  or universe, not through knowledge of an object key.
- Public avatar access must be limited to assets referenced by a currently
  public character. Prefer short-lived signed URLs or a dedicated public-asset
  route over making a bucket public.
- Copy avatar bytes to a new object key on import so deletion/unpublication of
  the source cannot mutate or delete the imported card's asset.

## 5. Ownership and creation architecture

### 5.1 Centralize world lifecycle ownership

Add a Layer 2 world lifecycle/registration capability used by every runtime
creation path. The simplest authority-preserving design is to extend
`CanonKeeper.create_multiverse` and `CanonKeeper.create_universe` with required
`owner_id` and have them coordinate Neo4j plus the Layer 1 Postgres registry.
CLI and UI callers pass identity explicitly; neither imports Postgres for this
purpose.

All runtime paths must migrate to this capability:

- `routers/universes.py` create and fork, including registration of the new
  fork under the caller, not the source owner.
- `routers/forge.py`, `ingest_shared.py`, and pack `apply/new-world`.
- Quick World and WorldArchitect.
- CLI `commands/universe.py` and `commands/play.py` through agent calls.
- CanonKeeper proposal commits, with `owner_id` stamped into the proposal and
  checked against its target universe before commit.
- Per-user Conversatory creation.

Direct `neo4j_create_multiverse`, `neo4j_create_universe`, and
`neo4j_fork_universe` calls must not remain in production callers outside the
central capability. Existing direct writes in tests can remain where they test
Layer 1 tools, but integration fixtures that exercise web authorization must
create registered worlds.

Neo4j and Postgres do not share a transaction. Use a documented compensating
sequence:

1. Validate the authenticated owner and parent multiverse.
2. Create the canonical Neo4j resource through CanonKeeper.
3. Insert its Postgres ownership row with the same ID and owner.
4. If registration fails, attempt canonical deletion/rollback through
   CanonKeeper and surface failure; record any remaining orphan for
   reconciliation. Never return a successful, inaccessible world.
5. Reconciliation can repair a canonical-node-without-row during controlled
   migration only. Normal requests must not auto-claim an orphan.

Update registry labels on rename and remove registry rows only after successful
canonical deletion. Deletion failures must not silently detach a still-live
world from its owner.

### 5.2 Shared authorization service

Add `packages/ui/backend/src/monitor_ui/ownership.py` with async helpers such
as:

- `require_multiverse_owner(user, multiverse_id)`.
- `require_universe_owner(user, universe_id)`.
- `require_story_owner(user, story_id)`.
- `require_scene_owner(user, scene_id, expected_story_id=None)`.
- `require_play_session_owner(user, session_id, expected_universe_id=None)`.
- `require_character_owner(user, character_id, allow_public=False)`.
- `require_source_owner`, `require_pack_owner`, `require_job_owner`, and
  `require_chat_session_owner`.

Each helper returns an authorized resource/context for the handler to reuse,
avoiding a check-then-use second lookup with different filters. Nested routes
must validate the entire chain. For example, a snapshot ID must belong to the
path universe; a scene added to a play session must belong to that session's
story/universe; a persona and target character must both be accessible to the
caller.

Add owner-scoped data-layer methods for rootless records and list-by-ID support
for Neo4j roots. For universe lists, obtain the owner's IDs in Postgres and add
an ID predicate to Neo4j before `SKIP/LIMIT`; do not fetch the newest 200
worlds globally and discard unauthorized results afterward. Apply the same
rule to multiverse, story, chat, character, source, job, pack, and library
lists.

Use explicit `owner_id` arguments through agents and background jobs. Do not
use a mutable process-global “current user” or ContextVar as the sole carrier
of identity across executor threads.

### 5.3 Route policy inventory

Before enforcement, generate a checklist from FastAPI's actual routes and
classify every one:

| Policy | Routes/resources |
|---|---|
| Public | Liveness health, signup, login; no private deep-health details |
| Authenticated global read | Built-in game systems, built-in tones/prompts, playtest benchmark definitions |
| User-owned | Universes/multiverses and all descendants, chats, characters, sources, packs, jobs, custom libraries, preferences |
| Public-or-owner | Published character card detail/export/avatar/import only |
| Operator/admin | Database connection settings, LLM provider secrets/configuration, global cache clear, force-unlock, global performance/process controls |

`/api/auth/logout`, token management, and `/api/auth/me` require their obvious
authenticated policies. The Next.js catch-all proxy is not an authorization
boundary.

Add a route-policy completeness test so a newly added route fails until it is
classified and has the expected dependency/handler authorization. Include
WebSockets and included/nested routers in the inventory. Built-in global reads
still require authentication when auth is enabled; admin authorization must not
be inferred from possession of an ordinary user account.

## 6. Phased implementation

Each phase has a mergeable vertical slice and an exit gate. Do not enable final
`NOT NULL` constraints or broad authorization until the corresponding backfill
has been verified.

### Phase 0 — Characterization, inventory, and use cases

- Add the route/resource inventory and current-behavior characterization tests
  where they will not codify insecure behavior as the target contract.
- Add `SYS-13` Account and identity lifecycle, `SYS-14` Browser/API
  authentication, `SYS-15` Cross-tenant isolation, `SYS-16` Private chat and
  realtime sessions, and `SYS-17` Public character gallery/import under the
  System epic. Confirm IDs are still free at implementation time.
- Update `docs/USE_CASES.md` ranges and amend `SYS-6` for per-user preferences.
- Add test fixtures that build two users and independent clients, including
  separate cookie jars and API tokens.
- Document which existing tests use local auth-disabled mode and which must run
  with auth enabled. Do not modify sealed suites under `tests/verification` or
  `tests/property`.

**Exit:** every current route and storage family has an owner/public/operator
classification; new use-case specifications state allow and deny behavior.

### Phase 1 — Identity schema and migration runner

- Implement numbered Postgres migrations, users/auth sessions/API tokens,
  multiverse registry, nullable world ownership, and the new per-user
  preference table.
- Add Layer 1 user schemas and owner-scoped Postgres methods. Fix the existing
  `worlds_list` ordering bug (`ORDER BY name` despite a `label` column) while
  adding mandatory owner filters to externally used list methods.
- Extend `world_upsert` so owner and parent are written on insert and cannot be
  silently reassigned by an update. Use separate explicit administrative
  ownership-transfer methods later if ever needed.
- Add Mongo scope fields/index creation as idempotent migration steps, but do
  not expose public visibility yet.
- Implement `argon2-cffi` password helpers and normalization with unit tests.

**Exit:** mocked Layer 1 tests pass; a real-Postgres integration test upgrades
the current schema, runs migrations twice, and verifies constraints and rollback
on an intentionally failing migration.

### Phase 2 — Authentication and request security

- Add `monitor_ui/auth.py`, token service, and `/api/auth/signup`, `/login`,
  `/logout`, `/me`, and API-token management routes.
- Add cookie and bearer principal resolution. API tokens are for API clients;
  browser cookie mutations use CSRF protection. Validate `Origin`/`Referer`
  against configured origins and require a CSRF token or equivalent
  double-submit header on unsafe cookie-authenticated requests. Do not treat
  CORS as CSRF protection.
- Reject wildcard credentialed CORS origins. Configure secure cookies and
  trusted proxy behavior explicitly in `UISettings`, with examples in
  `env.example` and deployment docs.
- Add generic login failures, signup conflict handling, bounded inputs,
  expiration/revocation checks, auth rate limiting, and audit logs containing
  user IDs/token IDs but no secrets.
- Add local-auth-disabled resolution and a loud startup warning. Keep public
  liveness minimal; deep component status is operator-only.
- Protect `/api/v1/chat/completions` with API tokens and enforce resource
  ownership in both plain and session modes. Add per-user invocation limits.

**Exit:** two browser clients have independent sessions; logout/expiry/
revocation deny further calls; bearer clients cannot use cookie-only CSRF
bypasses; password hashes/raw tokens never appear in responses or logs.

### Phase 3 — World registration, backfill, and root authorization

- Implement centralized CanonKeeper world registration and migrate every
  creation/fork/commit path listed in section 5.1.
- Add multiverse/world ownership helpers and owner-before-pagination list
  queries.
- Write the idempotent migration/backfill tool with `--dry-run`, batching,
  progress, and a machine-readable summary. It creates missing multiverse and
  world rows, assigns only NULL ownership to the local user, and never
  overwrites an existing different owner.
- Backfill every canonical root, including forks, hidden Conversatories, Quick
  Worlds, pack-created worlds, and template worlds. Report Neo4j nodes without
  rows, rows without nodes, parent mismatches, and duplicate names without
  treating names as identity.
- Enforce owner checks across universe/multiverse CRUD, state, seed, fork,
  snapshots/restore/compare, stories/scenes, graph, and universe-scoped search.
  Verify secondary IDs such as snapshot and scene belong to the path parent.

**Exit:** backfill counts reconcile exactly; A cannot list/read/mutate B's
multiverse/universe/story/scene/snapshot; all creation paths produce registered
rows before returning success.

### Phase 4 — Remaining routers and rootless user data

Apply authentication and ownership to all route groups, not just those with a
`universe_id` path parameter:

- Entities/NPC profiles/character sheets, parties, canon review, change log, GM
  tools/notes, lorebook, prompt collections, random tables, tone, Forge,
  Architect, images, and character promotion.
- Sources/uploads/rescan/delete, ingestion jobs, pack library, and all
  apply/clone/merge/slice/import/export paths. Validate every source pack and
  target universe in one action.
- User-authored game systems and libraries versus read-only built-ins. Add
  `owner_id` to rootless custom records or bind them to an owned universe.
- Global semantic search and Qdrant payload repair/reindex.
- Preferences and any active mode/context that is user-specific. Keep true
  deployment-wide provider/database configuration operator-only.
- Image generation and asset approval/download, including per-user budget
  accounting. Validate character, entity, scene, and universe references
  together.

Persist `owner_id` into ingest queue entries and jobs at submission. Include it
in placeholders, status lists, cancellation, cleanup, and worker-created world
registration. Operator watchdog/recovery may process all jobs internally, but
its web controls are admin-only and its user-facing output remains scoped.

**Exit:** the route completeness test passes; two-user tests cover indirect
reference substitution, exports, background jobs, vector search, custom
libraries, and assets as well as basic CRUD.

### Phase 5 — Chat, WebSockets, and per-user Conversatory

- Add owner-scoped chat persistence and per-user Redis indexes. Change
  `ensure_sessions_loaded` and `_db_load_sessions` to require owner; an
  in-process cache containing multiple users must still list only the caller's
  sessions.
- Authorize before reading messages, recaps, state, or loop caches and before
  every mutation (`send`, `begin`, `greet`, `wrap-up`, `end-scene`, `skip`, patch,
  delete). Validate universe, story, character, controlled characters, persona,
  prompt collection, and game-system references during session creation.
- Make durable updates owner-predicated. Do not let a session ID in a message
  body select another user's session.
- Authenticate and authorize WebSockets **before `accept()`** and before
  subscriber/Redis-listener registration. Close unauthorized connections with
  code `4401` and foreign/missing sessions with `4404`.
- Revalidate the auth session on inbound turn-producing frames and periodically
  for long-lived subscriptions; close on expiry/revocation. Heartbeats need not
  hit the database, but must not extend an expired session.
- Ensure the deployed WebSocket ingress forwards the same-origin session
  cookie. The Next.js HTTP route handler does not proxy upgrades. Test the real
  reverse-proxy/`NEXT_PUBLIC_WS_URL` path rather than assuming cookies from a
  different host will be sent.
- Replace `_conversatory_universe_id` with an owner-keyed mapping. Create one
  registered hidden host multiverse/universe per user and make its player
  identity/relationship state per-user. Hidden worlds are excluded from normal
  lists but remain owned and auditable.
- Scope standalone conversations and in-memory `_LOOPS` by verified owner and
  character. Resume/redistill/end must query by conversation, owner, and
  character, not conversation ID alone. Cross-incarnation recall is limited to
  versions of that same owner's card.

**Exit:** A receives none of B's session lists, messages, cache hits, Redis
fanout, WebSocket frames, character memories, or Conversatory content, including
after backend restart and Redis warm-up.

### Phase 6 — Public standalone character gallery

- Extend character schemas/storage with owner and publication fields and make
  all existing private CRUD, import-card, export, expand/version, memories,
  lorebook, image, and conversation routes owner-aware.
- Add authenticated gallery list/detail endpoints, owner-only publish/unpublish,
  and import. Register static `/characters/public...` routes before dynamic
  `/characters/{character_id}` routes where necessary.
- Use separate public response models that expose only intended card fields and
  safe author/display metadata. Do not expose private versions, memory counts,
  universe IDs, object keys, or operational timestamps unnecessarily.
- Publish validates the stored owner and records explicit publication. Import
  copies the current published card/lorebook/avatar into a new private card,
  remaps IDs, and records optional source attribution.
- Importing from a universe NPC requires ownership of both the source entity's
  universe and the destination card operation. Publishing is never a side
  effect of ordinary update/import.
- Add gallery UI with publication warning, private/public state, import action,
  and clear distinction between a card and its private runtime incarnations.

**Exit:** B can see/import A's published card but cannot enumerate A's private
cards or receive A's memories, versions, conversations, private lorebook, or
source object keys. Imported content remains independent after source edit,
unpublish, and deletion.

### Phase 7 — Frontend, CLI, and local-development compatibility

- Add login/signup/logout, current-user state, safe return-to handling, API
  token management, and an auth provider using the existing React Query
  dependency. Redirect on 401 but treat this only as UX; backend checks remain
  authoritative.
- Update world/source/pack/chat lists to “my” framing and handle empty/forbidden
  states without retry loops. Add gallery and publication controls.
- Ensure the Next.js proxy forwards `Set-Cookie`, CSRF headers, and credentials
  without caching auth responses. Keep bearer tokens out of localStorage for
  ordinary browser sessions.
- Add a Layer 2 local-identity service for CLI. CLI world creation passes the
  fixed local owner through CanonKeeper; no CLI-to-Postgres import is added.
- Provide operator-only local scripts to set the local account password
  interactively and to grant/revoke admin for an explicitly identified existing
  user. Never bootstrap admin from the first signup. Do not accept passwords in
  shell arguments or log them; record admin changes in an audit log.
- Document auth-disabled development, production enablement, reverse proxy/
  WebSocket cookies, backup, migration, verification, and rollback in
  `docs/5_infrastructure/` and `env.example`.

**Exit:** fresh signup and upgraded solo-install flows work in a real browser;
CLI-created worlds appear only under the same local account in the web UI;
layer-boundary checks pass.

### Phase 8 — Enforcement, cleanup, and release

- Run the full backfill again immediately before enforcement to catch rows
  created by older writers. During rolling deployment, stop old writers or
  ensure every writer already performs dual registration.
- Assert zero unowned runtime roots and zero rootless private documents without
  an owner. Quarantine unresolved records; never auto-assign them to whoever
  requests them.
- Enable authorization for every classified route, then make registry ownership
  columns `NOT NULL` in the final migration.
- Switch old global Redis indexes out of use with versioned keys. Keep old
  tables/keys read-only or unused for one release; destructive deletion is a
  separate later migration after backups and confirmation.
- Leave `active_world` and `world_db_bindings` untouched and unreferenced.
  Their removal is unrelated cleanup, not part of the security release.

**Exit:** all release gates in section 8 pass with auth enabled and with the
explicit local development mode tested separately.

## 7. Backfill and operational runbook

Use one auditable `scripts/migrate_multi_tenancy.py` entry point (or clearly
linked subcommands) rather than unrelated one-off patches.

1. **Prepare:** back up Postgres, Neo4j, MongoDB, Qdrant, and object storage;
   record versions; deploy migration-capable code with enforcement off; stop or
   upgrade old writers.
2. **Dry run:** report counts for canonical roots, missing registry rows,
   rootless documents, vectors lacking scope, and conflicts. Confirm the fixed
   local account is the intended legacy owner.
3. **Expand/backfill:** create the local user with an unusable random password;
   create missing registry rows and owner fields; default all visibility to
   private; migrate preferences and rootless records; rebuild required indexes
   and vector metadata.
4. **Verify:** rerun reconciliation. Require zero unexplained differences and
   no ownership overwrites. Review hidden/system worlds explicitly.
5. **Enforce:** deploy authorization to all workers, run two-user smoke tests,
   then apply `NOT NULL` constraints. Keep auth enabled during this step;
   `MONITOR_AUTH_DISABLED` is not a safe rollout shortcut on a reachable host.
6. **Enable user access:** operators either use new accounts for fresh installs
   or set the local account password interactively for an upgraded solo
   install. Do not email or log a generated password.
7. **Rollback:** roll back application code only while retaining compatible
   additive schema and ownership fields. Never roll back by disabling auth on
   populated multi-user data. Restore from backups only through an explicit
   operator disaster-recovery decision.

The script must be resumable and idempotent, log IDs/counts rather than private
content, and fail on ambiguous ownership. A second run should make no changes.

## 8. Test and verification plan

### 8.1 Unit and API tests

Add tests in allowed package/unit/API locations, mapped to the new use cases:

- Password hash/verify/rehash, normalization, duplicate signup races, session
  expiration/rotation/deletion, API-token expiry/revocation, and local-mode
  resolution.
- Cookie attributes, CSRF/origin rejection, CORS configuration, rate limits,
  and secret-free response/log behavior.
- Every ownership helper's allow/missing/foreign/mismatched-parent cases.
- Owner-before-pagination queries, empty allowed-ID sets, and no unscoped
  fallback when storage/cache calls fail.
- Mongo read/update/delete predicates, Redis per-user indexes, Qdrant mandatory
  filters, and object-asset authorization.
- Public character response allowlist and import field exclusion/remapping.
- Route inventory completeness, including new routes and WebSockets.

Run existing backend tests with explicit test auth fixtures. Do not weaken old
assertions or bypass all dependencies globally merely to avoid updating test
setup.

### 8.2 Two-user integration matrix

Against real Postgres, Neo4j, MongoDB, Qdrant, Redis, and MinIO where available,
create users A and B and independent resources. For every resource family,
verify:

1. A sees and operates on A's resource.
2. B's lists/counts/searches contain no A IDs or metadata.
3. B gets the same generic `404` for A's ID and a nonexistent ID on get,
   update, delete, export, and action routes.
4. B cannot use A's ID as a parent, source, target, persona, snapshot, scene,
   pack, character, or other secondary reference in B's own request.
5. Missing/unmigrated ownership denies access rather than falling back.
6. Cached and uncached paths behave identically. Repeat after warm Redis,
   backend restart, and a second backend worker where supported.
7. Background jobs retain the submitter's owner and cannot be read/cancelled by
   the other user.
8. WebSocket connect, inbound messages, logout/expiry, and cross-process Redis
   fanout enforce the same isolation.

Include explicit tests for universe fork, pack apply/new-world, Quick World,
WorldArchitect/CanonKeeper commit, CLI local creation, per-user Conversatory,
standalone conversation resume, semantic search, image download, and public
card import independence.

### 8.3 Browser and migration verification

- Browser: signup A → create world/card/chat → signup B in a separate browser
  context → verify isolation → publish A's card → import as B → verify private
  runtime state remains separate → logout and verify 401/WebSocket closure.
- Upgraded install: seed pre-migration data → dry-run → backfill twice → verify
  zero changes on second run → enable auth → set local password interactively →
  confirm only the local account owns legacy data.
- Fresh install: no migration dependency, no default admin, no legacy world
  assigned to the first signup.
- Real ingress: verify secure cookies and same-origin WebSocket authentication
  through the documented reverse proxy, not only FastAPI `TestClient`.

### 8.4 Standard checks

Run the relevant focused tests during each phase, then before release:

```bash
uv run pytest packages/data-layer/tests/test_db/test_postgres.py -q
uv run pytest packages/ui/backend/tests -q
uv run pytest packages -q
RUN_INTEGRATION=1 uv run pytest tests/ -q
uv run ruff check packages
uv run ruff format --check packages
uv run mypy packages/*/src --cache-dir /tmp/mypy-cache
python scripts/check_layer_dependencies.py
```

For the frontend, use its existing package manager/lockfile to run
`npm run test`, `npm run type-check`, and `npm run build` (or the equivalent
scripts through the locked package manager). Run gated e2e tests with both
`RUN_INTEGRATION=1` and `RUN_E2E=1` as required by their fixtures.

No phase is complete while its new isolation tests are red or while any route
remains unclassified.

## 9. Critical files

Core additions and changes are expected in:

- `packages/data-layer/src/monitor_data/db/postgres.py`
- `packages/data-layer/src/monitor_data/schemas/users.py` (new)
- `packages/data-layer/src/monitor_data/schemas/vectors.py`
- `packages/data-layer/src/monitor_data/tools/qdrant_tools.py`
- `packages/data-layer/src/monitor_data/tools/mongodb_tools/`
- `packages/agents/src/monitor_agents/canonkeeper/agent.py`
- `packages/agents/src/monitor_agents/quick_world/agent.py`
- `packages/agents/src/monitor_agents/world_architect/agent.py`
- `packages/ui/backend/src/monitor_ui/auth.py` (new)
- `packages/ui/backend/src/monitor_ui/ownership.py` (new)
- `packages/ui/backend/src/monitor_ui/config.py`
- `packages/ui/backend/src/monitor_ui/main.py`
- `packages/ui/backend/src/monitor_ui/routers/` (full inventory, not a subset)
- `packages/ui/backend/src/monitor_ui/routers/character_storage.py`
- `packages/ui/backend/src/monitor_ui/routers/character_conversation.py`
- `packages/ui/backend/src/monitor_ui/routers/chat_persistence.py`
- `packages/ui/frontend/src/app/api/[...path]/route.ts`
- `packages/ui/frontend/src/lib/api.ts`
- `packages/cli/src/monitor_cli/commands/universe.py`
- `packages/cli/src/monitor_cli/commands/play.py`
- `scripts/migrate_multi_tenancy.py` (new)
- `docs/USE_CASES.md`, `docs/use-cases/epic-11-system-SYS/`, and
  `docs/5_infrastructure/`

`schemas/entity_templates.py` should require only ownership-related changes
through its existing universe contract; it should **not** receive the optional
universe/public-gallery redesign from the earlier draft.

## 10. Future multiplayer seam

Multiplayer remains a separate design and implementation effort. This plan
neither claims that existing fanout provides multiplayer nor adds an unused
collaborator table.

A future design must address:

- A participant roster and role/permission model for worlds and play sessions.
- `speaker_id`/player identity in turn contracts, `GMAgent.decide`, `SceneState`,
  and DSPy signatures.
- Locking or a durable action queue around scene turns and process-local
  session/loop state.
- Mapping connected humans to controlled combatants and multi-actor context
  assembly/memory filtering.
- Authorization on every published event, reconnect, resume, and proposal
  commit, including revocation of an existing participant.

Stable user IDs, explicit per-request principals, owner-scoped WebSocket
admission, and per-user cache keys are useful foundations. They are not a
substitute for that future concurrency and sharing model.
