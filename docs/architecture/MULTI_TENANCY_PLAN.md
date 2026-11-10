# Multi-Tenancy — Implemented State

> **Status:** rewritten 2026-11-10 (Phase 6, multi-tenant hardening) to describe
> what **is implemented**, what is **enforced where**, and what **remains**;
> updated the same day by the gap-closing pass (owner assertions below the
> HTTP layer, per-model-call usage accounting and in-turn quota enforcement).
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

### Owner context and tool-boundary assertions (Phase 6 task 8)

Ownership is no longer enforced at the HTTP layer only:

- The acting owner travels in a `contextvars.ContextVar`
  (`monitor_data.tenancy`), bound by the UI backend for the duration of
  every authenticated HTTP request and every WebSocket turn
  (`monitor_ui.auth.resolve_principal`), and explicitly unbound in
  `MONITOR_AUTH_DISABLED` local mode. It survives `asyncio.to_thread` /
  `anyio.to_thread` and the LangGraph nodes the loops run (nodes execute
  under `copy_context()`); where the context cannot cross (background
  `run_coroutine_threadsafe` loops), callers capture the owner first and
  pass it explicitly. `SceneLoop`, `StoryLoop` and `ConversationLoop`
  additionally take `owner_id` from the session doc (stored on the loop and
  on `SceneState` / `StoryState` / `ConversationState`) and bind it around
  every turn.
- The most-used write tools assert at the tool boundary that the target
  universe (or the resource's universe) belongs to that owner in the
  Postgres registry, and refuse the write with `OwnerViolationError` when it
  does not — a missed HTTP guard fails closed. Covered tools: story
  (`mongodb_create_story_outline`, `mongodb_update_story_outline`,
  `mongodb_append_story_ledger_entry`), scene/turn (`mongodb_create_scene`,
  `mongodb_update_scene`, `mongodb_append_turn`,
  `mongodb_update_turn_resolution`), character/entity
  (`mongodb_create_character_sheet`, `mongodb_update_character_sheet`),
  memory (`mongodb_create_memory`, `mongodb_update_memory`,
  `mongodb_delete_memory`), NPC profile (`mongodb_create_npc_profile`,
  `mongodb_update_npc_profile`), and proposed change
  (`mongodb_create_proposed_change`, `mongodb_update_proposed_change`,
  `mongodb_defer_proposed_change`, `mongodb_edit_proposed_change`,
  `mongodb_flag_proposal_review`).
- No owner in context (local mode, scripts, ingestion workers, tests) means
  no assertion — existing behavior there is unchanged. The HTTP layer maps
  `OwnerViolationError` to the same generic 404 the guards return (plan D4).

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

- Spending is counted **per model call**, not per HTTP request: after every
  model call the LLM runtime (and every other direct model-call site) adds
  the prompt/completion tokens plus one call to the owner's daily usage
  (`PostgresClient.usage_record`) via `monitor_data.usage`. A failed usage
  write is logged and recorded (roleplay error), never raised into the turn.
  Covered call sites: `monitor_agents.dspy_runtime` (one decorator on
  `CachedDSPyLM.__call__`), `monitor_agents.llm_registry.LLMClient`
  (`create` / `complete_text` / `stream_text`), `players/instructable_player`,
  retrieval `pair_llm` / `embedder` / `embedding_health`, and the image
  providers (one call per image, no tokens).
- Enforcement is shared: `monitor_data.usage.enforce_usage_quota` raises the
  typed `QuotaExceededError` at the cap, both **before every model call**
  (in-turn enforcement: the next model call of an over-budget owner fails)
  and from `monitor_ui.auth.usage_quota_guard`, the pre-request face of the
  same check mounted on the model-spending routes (chat turns, image
  generation, LLM-backed entity routes, and `/v1/chat/completions`).
  Caps come from `MONITOR_DAILY_TOKEN_CAP` / `MONITOR_DAILY_CALL_CAP`
  (unset = no cap); a per-user override (`user_usage_limits`, admin-managed,
  `exempt` flag) wins over the env defaults. Admins and the local account
  are never capped. Admin view/change: `GET /api/admin/usage`, `GET/PUT
  /api/admin/usage/{user_id}[/limits]`.
- Error surfaces: the typed refusal maps to a readable `429` on HTTP (an
  app-level handler in `monitor_ui.main`) and to a readable `error` event on
  the chat WebSocket (`error_class: "quota_exceeded"`). The scene
  orchestrator maps an in-turn refusal onto the existing
  `llm_provider_error` event path, and the Narrator re-raises the typed
  error instead of degrading to draft text.
- WebSocket chat turns are charged through the same per-model-call
  accounting (each turn's model calls record usage; there is no separate
  per-turn fee), so WS spend can no longer bypass the cap.

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
| Agent/data layers | acting-owner context + per-loop `owner_id` | `monitor_data/tenancy.py`, `loops/*` |
| Tool boundary | `assert_*_write` on the most-used write tools (fail closed) | `monitor_data/tenancy.py`, `tools/mongodb_tools/*` |
| Search/graph | owned-ID predicates inside the storage queries | `routers/search.py`, `routers/graph.py` |
| Quota | per-model-call recording + pre-call `QuotaExceededError` | `monitor_data/usage.py`, `monitor_agents/dspy_runtime.py`, direct model-call sites |
| Quota | pre-request `usage_quota_guard` on model-spending routes | `monitor_ui/auth.py`, `routers/openai_compat.py` (router line) |
| Error mapping | `QuotaExceededError` → 429 / WS `error` event; `OwnerViolationError` → 404 | `monitor_ui/main.py`, `routers/chat.py`, `loops/scene_orchestrator.py` |
| Registry | Postgres `owner_id` columns + `worlds.kind` | `monitor_data/db/postgres.py` |
| Secrets | Fernet encryption in the provider read/write path | `monitor_data/db/postgres.py` |
| Tests | route-coverage, cross-tenant sweep, tool guards, loop propagation, usage accounting | `packages/ui/backend/tests/`, `packages/data-layer/tests/`, `packages/agents/tests/` |

## 4. What remains

### Defense in depth beyond the covered write tools (Phase 6 task 8 — done for the named surface)

The interface sketched for the follow-up phase is implemented: write tools
assert the acting owner against the Postgres registry (via
`monitor_data.tenancy`, `expected_owner_id` supported for explicit
forwarding), and the loops pass the session owner (constructor `owner_id`,
stored on state). What remains is breadth, not mechanism:

- Write tools outside the six named families (combat, resolutions,
  lorebook, game systems, knowledge packs, play sessions, visual identities,
  conversation turns, …) are still only covered by the HTTP guards. They
  can adopt the same `assert_*_write` calls incrementally.
- Standalone character-card writes live in the UI routers
  (`character_storage.py`) and are owner-predicated there; no data-layer
  write tool exists to guard yet.
- `BaseAgent.call_tool` surfaces a tool refusal at the MCP boundary as an
  error string (pre-existing behavior for all tool errors): the write fails
  closed, but agent code that ignores the returned text will not see an
  exception. Loops that call tools directly (SceneLoop, StoryLoop) get the
  typed `OwnerViolationError` propagating.

### Known gaps and limits

- **Mid-stream quota errors.** An in-turn `QuotaExceededError` maps to 429
  on HTTP and to a readable error event on the chat WebSocket; inside an
  already-open SSE stream (OpenAI-compat/light-RP streaming) the error
  surfaces as an aborted stream rather than a 429 status.
- **Blanket handler catches.** A few endpoints normalize all exceptions to
  502; `routers/entities.py` (draft) re-raises the typed tenancy errors so
  the 429/404 mappings hold, others may still wrap them (list: image-gen
  handlers, gm_tools LLM routes).
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
