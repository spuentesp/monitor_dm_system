# UI Revamp & Play-First Repair Plan (FINAL_FABLE Phase 6)

> **Created:** 2026-06-12, from a live diagnosis of the console-error storm and
> the "I can't even talk to an LLM" session. Tasks T-049+ in
> `FINAL_FABLE_TASKS.md`. Goal hierarchy: **(A) you can play a roleplay
> session and build a world conversationally, reliably** → (B) the UI stops
> being an error firehose and becomes coherent → (C) every remaining use case
> gets a real surface.

## What the console errors actually were (diagnosed, not guessed)

| Symptom | Root cause | Class |
|---|---|---|
| `401 login fail: carry the API secret key` on every narration | Settings "save provider" blanks stored API keys: the update handler merges `api_key: ""` over the saved key; DSPy then sends `"not-needed"` | **Backend bug** |
| `GET /api/health/databases` 404 (every few seconds) | `ConnectionStatus.tsx` polls a route that never existed; real routes are `/api/health` and `/api/databases` | Frontend bug |
| `GET /api/stories/{id}` 404 + infinite retry spam | `get_story` only reads LangGraph checkpoint state — a story that hasn't run a StoryLoop turn 404s even though it exists in Neo4j; StoryPanel polls forever | Backend semantics + frontend retry policy |
| `GET /api/ingest/packs` 500 | Real server error (traceback captured during repair) | Backend bug |
| `GET /api/entities/systems/{id}` 503 | `_query_systems` failure path | Backend bug |
| CORS / `ERR_CONNECTION_RESET` / WebSocket drops | The backend container was being rebuilt under your session — transient, not a code bug. CORS headers vanish when the connection dies mid-flight | Operational |
| Ingestion "expected dim 1536, got 0" | An embedding path can hand Qdrant an empty vector | Backend bug |

## Phase 6A — Play-first repairs (do first, in this order)

1. **T-049 Provider keys survive edits.** `update_provider` must ignore
   empty-string `api_key`/secrets (treat as "unchanged"). Re-key the damaged
   MiniMax rows. Pass `MINIMAX_API_KEY`/`MINIMAX_BASE_URL` through compose so
   even blanked rows fall back to env. Verify all three MiniMax rows test OK
   *from inside the container*, then verify a real narrated turn.
2. **T-050 Story endpoint stops lying.** `GET /stories/{id}` falls back to the
   Neo4j story record (fresh stories have no checkpoint state yet); 404 only
   when the story genuinely doesn't exist.
3. **T-051 Frontend error hygiene.** React-Query defaults: never retry 4xx,
   stop `refetchInterval` polling after repeated failures; ConnectionStatus
   uses `/api/health`; global query errors surface as a single toast, not
   console spam.
4. **T-052 Packs list 500** — fix from traceback.
5. **T-053 Systems detail 503** — fix `_query_systems` failure path.
6. **T-054 Embedding guard.** No empty vectors can reach Qdrant: validate at
   the upsert boundary, regenerate via local fallback, log the offending text.
7. **T-055 Verified play pass.** With the above deployed: create session →
   roll character → 3 narrated turns → end scene (UI path, MiniMax default);
   create-world-by-chat in World Architect mode produces entities in the
   graph. Both verified via API and recorded in STATUS.md.

## Phase 6B — UI coherence overhaul

8. **T-056 One world context.** A global world/universe picker in the
   sidebar (persisted); every page (Play, Forge, Worlds, Snapshots, Explorer,
   GM) reads it instead of each page maintaining its own selectors.
9. **T-057 Onboarding flow.** Empty-state home: "Create a world → seed or
   ingest → make a character → play" wizard wired to the demo machinery
   (`demo_millhaven.py` logic exposed as "Try the demo world" button).
10. **T-058 Error & loading language.** Shared `<QueryBoundary>` per panel:
    skeletons while loading, one inline retry card on failure, toasts for
    mutations; kill remaining raw `fetch()` calls (audit found several).
11. **T-059 Session manager.** Play page: rename/archive sessions, show
    universe + story binding and phase; resume cleanly after backend
    restarts (WS auto-reconnect with backoff + "reconnected" toast).
12. **T-060 Settings truthfulness.** Provider cards show key-presence
    ("key saved · from env · missing") instead of silently saving blanks;
    role badges; a "test all" button; node-assignment editor (the audit gap).

## Phase 6C — Use-case completion (the remaining dark corners)

13. **T-061 Pack ops UI**: merge / export / import / clone / slice from the
    Pack Library (endpoints exist, no buttons).
14. **T-062 Ingest job controls**: unlock / cancel / purge actions + live
    stage log viewer (jobs already stream stages).
15. **T-063 Batch entity UI**: multi-select in Worlds → bulk tag/delete
    (batch endpoints exist).
16. **T-064 Audit trail (Q-10)**: change_log tool layer + a History tab on
    entity/universe pages (schemas + contract tests already exist).
17. **T-065 Playwright flows**: extend smokes to 3 interaction tests —
    create-session-and-send, forge-upload, canon-accept.

## Acceptance for "revamp done"

- Browser console clean (zero red) through: home → create world → ingest doc
  → play 5 turns → end scene → GM tools → snapshots.
- All providers in Settings show accurate key state; editing never destroys
  credentials.
- Playwright interaction flows green in nightly CI.
