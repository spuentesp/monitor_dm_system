# Multi-Tenancy — Implemented State

> **Status:** rewritten 2026-11-10 (Phase 6, multi-tenant hardening) to describe
> what **is implemented**, what is **enforced where**, and what **remains**.
> The original design narrative lives in
> [MULTI_TENANCY_IMPLEMENTATION.md](MULTI_TENANCY_IMPLEMENTATION.md).
>
> **Goal.** A second person can be given an account without being able to read
> or change the first person's worlds, spend their model budget without limit,
> or read stored provider keys.

## 1. What is implemented

### Identity and request security (Phase 1)

- Accounts, opaque browser sessions (cookie holds the raw token, Postgres stores
  only its SHA-256 hash), per-user revocable API tokens (`Authorization:
  Bearer`), Google OAuth, CSRF double-submit, login/signup rate limits, an
  admin role, and banning.
- `MONITOR_AUTH_DISABLED=true` resolves every request to a fixed local admin
  (`monitor_ui.auth.LOCAL_USER_ID`) — a local-development exception only.

### Ownership registry and resolvers (Phases 1–6)

- Postgres is the ownership registry: `multiverses.owner_id` and
  `worlds.owner_id` (`packages/data-layer/src/monitor_data/db/postgres.py`);
  world-descendant data inherits through the validated `universe_id` chain.
  `worlds.kind` (`world` | `conversatory`) marks the per-user Conversatory host.
- `monitor_ui/ownership.py` maps path/query parameter names to ownership
  resolvers (`_SCOPE_RESOLVERS`) and applies them through
  `resource_route_guard`, a router-level dependency. Resolvers cover:
  universe, multiverse (`multiverse_id`, `mv_id`), story, scene, entity,
  fact/axiom/event, relationship, character sheet, character (standalone card
  or world entity), chat session, play session, conversation, ingestion job
  (`job_id`, `ingestion_job_id`), ingest source, proposal, knowledge pack,
  party, lorebook entry, template (entity **and** character templates),
  generated asset, prompt collection.
- Fail closed everywhere: a foreign or missing private ID returns the same
  generic `404 Not found` as a nonexistent ID; empty owned-ID sets return
  empty lists, never unscoped fallbacks.

### Route guards (Phase 6)

- Every router mounts a router-level auth dependency: `resource_route_guard`
  (auth + ownership resolution) on user-facing routers, `require_admin` on the
  operator surface (admin, llm, databases, jobs, performance, prompts). The
  `auth` router is the documented exception — its public routes (login,
  signup, config, OAuth) carry no auth dependency and are listed in the
  explicit `PUBLIC_ROUTES` allowlist in
  `packages/ui/backend/tests/test_route_auth_coverage.py`; its guarded routes
  carry route-level dependencies.
- The chat WebSocket moved to `chat.ws_router` so its handshake keeps WS close
  codes (4401/4404) while the HTTP routes carry the guard.
- Structural enforcement: `test_route_auth_coverage.py` fails when any route
  with a resource-id parameter loses its guard, and when the public allowlist
  grows stale or gains a destructive method.

### Cross-tenant suite (Phase 6)

`packages/ui/backend/tests/test_cross_tenant.py`: two users A and B; per-kind
cases (universe, story, scene, chat session, play session, character, persona,
pack, ingest job, note, image, template, provider, API token, conversation)
assert B's read/list/update/delete of A's resource answers 404/403 and A's data
is unchanged. A sweep generated from the route table calls B on **every** route
carrying a resource-id parameter — new routes are covered automatically; the
only exclusions live in `SWEEP_EXEMPT` with a stated reason.

### Per-user Conversatory (Phase 6)

- One hidden host universe per user, found through the ownership registry
  (`worlds.kind = 'conversatory'`) — never by name, never cached in a process
  global. `ensure_conversatory_universe(owner_id)`
  (`routers/character_conversation.py`) creates and registers it under the
  owner via CanonKeeper + `world_upsert`.
- `scripts/migrate_conversatory_per_user.py` re-homes incarnations from the
  legacy shared universe (idempotent, dry-run default).

### Search, graph, and OpenAI-compatible reads

- `/api/search` is always owner-scoped: pinned to an owned universe or
  restricted to the caller's owned-universe allowlist via a server-added Qdrant
  predicate.
- `/api/graph` scopes its Neo4j reads with the caller's owned universe/
  multiverse ID lists.
- `/api/v1/chat/completions` requires a caller-owned character and, on resume,
  a caller-owned conversation.

### Usage and quota

- Usage is recorded per user per UTC day (`user_usage_daily`) via
  `PostgresClient.usage_record(user_id, tokens=..., calls=...)`.
- `monitor_ui.auth.usage_quota_guard` charges one call per model-spending
  request and answers a readable `429` at the cap. Caps come from
  `MONITOR_DAILY_TOKEN_CAP` / `MONITOR_DAILY_CALL_CAP` (unset = no cap); a
  per-user override (`user_usage_limits`, admin-managed, `exempt` flag)
  wins over the env defaults. Admins and the local account are never capped.
  Mounted on the chat turn routes, image generation, and the LLM-backed
  entity routes.
- Admin view/change: `GET /api/admin/usage`, `GET/PUT
  /api/admin/usage/{user_id}[/limits]`.

### Provider keys

- `llm_providers.api_key` is Fernet-encrypted at rest when
  `MONITOR_PROVIDER_KEY_ENCRYPTION_KEY` holds a url-safe base64 32-byte key;
  when unset, keys stay plaintext and exactly one warning is logged at startup
  (`provider_api_keys_unencrypted`).
- Reads tolerate legacy plaintext rows;
  `scripts/migrate_encrypt_provider_keys.py` encrypts existing rows
  (idempotent, dry-run default, never prints keys).
- The API never returns a key after creation — responses show the last 4
  characters only.

### Process caches

- `_SESSIONS`, `_MESSAGES`, `_SCENE_LOOPS`, `_CONVERSATION_LOOPS` and the
  light-RP `_LOOPS` cache are reached only after an ownership check
  (`require_chat_session_owner`, `require_conversation_owner`) at the router;
  the cross-tenant suite seeds these caches so a missing check is a visible
  leak rather than an accidental 404.
- The Conversatory universe is no longer cached in a process global.

## 2. Design decisions (kept for the in-code "plan D3/D4/D5" references)

- **D1 — Self-serve email/password signup, server sessions, and API tokens.**
- **D2 — Strict private tenancy plus a standalone character gallery.**
- **D3 — Logical isolation, with canonical ownership in Postgres.**
  `multiverses.owner_id` / `worlds.owner_id`; descendants inherit through the
  validated `universe_id` chain.
- **D4 — Deny by default and hide private existence.** A foreign or missing
  private ID returns the same generic 404 as a nonexistent ID.
- **D5 — Explicit local identity for solo development.** `MONITOR_AUTH_DISABLED`
  resolves to one fixed local admin; legacy data backfills to it.
- **D6 — No speculative multiplayer schema.**

## 3. What is enforced where

| Layer | Mechanism | Files |
|-------|-----------|-------|
| HTTP routes | `resource_route_guard` + `_SCOPE_RESOLVERS` (router-level) | `monitor_ui/ownership.py`, every router |
| HTTP routes | explicit owner checks before handlers (defense in depth) | each router |
| WebSocket | `get_current_ws_principal` + `require_chat_session_owner` | `routers/chat.py` |
| Search/graph | owned-ID predicates inside the storage queries | `routers/search.py`, `routers/graph.py` |
| Quota | `usage_quota_guard` on model-spending routes | `monitor_ui/auth.py` |
| Registry | Postgres `owner_id` columns + `worlds.kind` | `monitor_data/db/postgres.py` |
| Secrets | Fernet encryption in the provider read/write path | `monitor_data/db/postgres.py` |
| Tests | route-coverage, cross-tenant sweep, structural guard check | `packages/ui/backend/tests/` |

## 4. What remains

### Defense in depth in the agent layer (Phase 6 task 8 — interface)

The HTTP layer is the only enforcement point today; agents and data-layer
tools take IDs and do not re-check an owner. The agent layer must thread the
owner through the most-used write tools (story, scene, character, memory) and
assert it, so a missed guard fails closed. Required interface for the phase
that owns `packages/agents` and the MCP tools:

```python
# packages/data-layer/src/monitor_data/tools/... write tools gain:
async def mongodb_create_memory(..., expected_owner_id: str | None = None) -> ...
    # assert the target story/scene/universe resolves to expected_owner_id
    # (via monitor_data.db.postgres world_get_for_owner), else raise ValueError

# packages/agents loops pass the session's owner from SceneState/session doc:
SceneLoop(..., owner_id=<session owner UUID>)  # forwarded to tool calls
```

Invariant: every write tool that names a universe/story/scene/character
accepts `expected_owner_id` and fails closed when it does not match the
registry. (CanonKeeper's Neo4j writes stay inside CanonKeeper; the assertion
belongs at the tool boundary it calls.)

### Known gaps and limits

- **WebSocket turn quota.** The chat WebSocket charges one call at handshake;
  individual WS messages are not charged and do not report tokens. The
  HTTP `send` route covers the non-WS client; a WS message counter needs the
  loop layer (other phase) to call `usage_record`.
- **Token accounting.** `usage_record(user_id, tokens=N)` is the write path
  for real token counts; wiring it to the LLM responses belongs to the LLM
  runtime (`monitor_agents.dspy_runtime` / `llm_registry`), which is outside
  this phase's file ownership. Until then only the call cap bites; the token
  cap is enforced over whatever has been recorded.
- **Providers are admin-owned and shared** (decision): non-admins get 403 on
  all `/api/llm` routes; admins manage keys for everyone.
- **Not done (out of scope):** organizations and shared worlds, billing,
  multiplayer in one scene, row-level security in the databases.
- Ingestion jobs are checked against `job.owner_id` **or** the owning
  universe (creator-friendly); the ingest router additionally enforces the
  strict creator match on its own routes.

## 5. Configuration reference

| Env var | Default | Meaning |
|---------|---------|---------|
| `MONITOR_AUTH_DISABLED` | `false` | local admin mode (never on a reachable host) |
| `MONITOR_PROVIDER_KEY_ENCRYPTION_KEY` | unset | Fernet key for `llm_providers.api_key`; unset = plaintext + one startup warning |
| `MONITOR_DAILY_TOKEN_CAP` | unset | daily token cap per user (UTC day); unset = no cap |
| `MONITOR_DAILY_CALL_CAP` | unset | daily model-call cap per user (UTC day); unset = no cap |

Per-user overrides (win over env): `user_usage_limits.daily_token_cap`,
`.daily_call_cap`, `.exempt` — admin-managed via `/api/admin/usage/{id}/limits`.

## 6. Migration runbook

1. `uv run python scripts/migrate_encrypt_provider_keys.py --apply` — encrypt
   existing provider keys (requires `MONITOR_PROVIDER_KEY_ENCRYPTION_KEY`).
2. `uv run python scripts/migrate_conversatory_per_user.py --apply` — move
   standalone-character incarnations into per-user Conversatory universes.

Both scripts are idempotent and dry-run by default. After (2), the legacy
shared "Conversatory" universe is unreferenced and can be removed by the
operator.
