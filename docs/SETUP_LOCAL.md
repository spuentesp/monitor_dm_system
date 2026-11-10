# Local setup — from clone to first turn

> **Scope.** Owner-machine development stack. Written 2026-11-10 from the commands
> actually run to bring up the stack on the owner's machine (Phase 0 of the
> roleplayable plan). For architecture see [docs/\_index.md](./_index.md); this
> file is only about getting a fresh checkout to a narrated turn.

## What you need installed

| Tool | Why | Check |
|------|-----|-------|
| Docker + docker compose v2 | infra services | `docker compose version` |
| `uv` | Python env | `uv --version` |
| Ollama | local chat + embeddings (free, no API key) | `curl -s localhost:11434/api/tags` |
| Node.js + npm | UI frontend (optional for API-only work) | `npm --version` |

## 1. Install the Python packages

```bash
uv sync
```

## 2. Create `.env`

```bash
cp env.example .env   # then edit: fill in the secrets you have
chmod 600 .env        # .env is gitignored — never commit it
```

Variables that must be right for a first turn (see `env.example` for the full
list and inline docs):

- `POSTGRES_*`, `MONGODB_URI`, `MONGODB_PASSWORD`, `QDRANT_URI`, `NEO4J_PASSWORD`,
  `MINIO_*`, `REDIS_URL` — service endpoints/credentials.
- `EMBEDDING_PROVIDER=ollama`, `EMBEDDING_MODEL=nomic-embed-text:latest`,
  `EMBEDDING_DIMENSION=768`, `EMBEDDING_BASE_URL=http://localhost:11434` — must
  match the active model pair and the Qdrant collection dimensions (see step 5).
  A missing `EMBEDDING_DIMENSION` silently defaults to 1536 and every write to
  Qdrant fails the dimension guard; a missing `EMBEDDING_BASE_URL` makes the
  ingest-doctor embedding probe report "base_url is empty".
- `MONITOR_AUTH_DISABLED=true` — **local development only**. Lets scripts
  (`scripts/live_gameplay_smoke.py`, curl) drive the API without a login. Leave
  it `false` (or unset) for anything reachable by other people; the browser flow
  then uses the normal signup/login at `/`.
- `NLP_BACKEND=spacy` (default) needs no NER service — when spaCy is not
  installed the NLP tools fall back to a dependency-free regex backend. Set
  `NLP_BACKEND=gliner` only together with the GLiNER container (step 3).

## 3. Start the infrastructure

```bash
make infra-up        # neo4j mongodb qdrant minio postgres redis, waits for ports
```

- **MinIO** is required when `STORAGE_BACKEND=minio` (the default). The compose
  file uses `bitnamilegacy/minio:latest` because `quay.io/minio/minio` cannot be
  pulled from this network (HTTP 401 on every tag, the same failure Weekly
  Integration hits in CI) and `docker.io/minio/minio` no longer exists. The
  S3 API listens on :9000; this image has no embedded web console.
- **GLiNER** is opt-in (the default NLP backend is spaCy, which needs no
  service):

  ```bash
  docker compose --env-file .env -f infra/docker-compose.yml --profile gliner up -d --build gliner
  ```

  The image bakes `urchade/gliner_base` plus its `microsoft/deberta-v3-base`
  backbone at build time (the previously pinned `knowledgator/gliner-base-v0.1`
  repository is gone from Hugging Face). Build needs network; runtime is
  hermetic.
- Never run `docker compose down -v` on a machine with shared data.

## 4. Start Ollama models

```bash
ollama pull llama3.2:1b          # LIGHT tier + HyDE/rerank
ollama pull qwen2.5:7b           # fallback STANDARD/HEAVY chat
ollama pull nomic-embed-text     # EMBEDDING tier (768-dim)
```

## 5. Providers, tiers and the active model pair

Every agent resolves its model by **tier** (`light`/`standard`/`heavy`/
`embedding`) against the `llm_providers` table: the row whose `role` matches is
used (the `is_default` row for that role is preferred), so you need at least one
*working* row per tier. `llm_node_assignments` is intentionally empty — nodes
fall back to their tier; add a row there only to pin one specific node.

1. Bring up the backend (step 7) and test each provider row:

   ```bash
   curl -X POST http://localhost:8000/api/llm/providers/<id>/test
   ```

   The test makes a live call and sets `status` (`connected` / `error`) and
   `latency_ms`. Set `is_default=true` on the row you want per tier (via
   `PUT /api/llm/providers/<id>` or the `/config` page).

2. Register the active model pair (the boot gate — the retrieval layer refuses
   to start without one):

   ```bash
   uv run python scripts/sync_pair_from_defaults.py --verbose
   # or pin explicitly:
   uv run python scripts/seed_model_pair.py --chat-model ... --embedding-model ...
   ```

3. If the embedding model or its dimension changed, rebuild the Qdrant
   vectors (safe when the collections are empty; `--dry-run` first):

   ```bash
   uv run python scripts/reindex_embeddings.py --dry-run
   uv run python scripts/reindex_embeddings.py --yes
   ```

Providers that answered on the owner's machine (2026-11-10): local Ollama
(`llama3.2:1b`, `qwen2.5:7b`, `nomic-embed-text`) and MiniMax `MiniMax-M2.7`
(via `MINIMAX_API_KEY`; the backend auto-creates the MiniMax rows from it on
first provider listing). Expired/dead rows left in `status=error`: Z.AI
(`token expired or incorrect`), GitHub Models and Google AI Studio (no keys),
MiniMax `M2-her` (404). Run `scripts/doctor.sh` to see what your machine
resolves today.

## 6. Verify the stack

```bash
./scripts/doctor.sh
```

Sections 1–3 are informational; **section 4 is the verdict** and exits non-zero
on: no active/incompatible model pair, a tier without a usable provider, an
unreachable store, or an embedding-dimension mismatch (`.env` vs pair vs live
Qdrant collections).

## 7. Run the UI

```bash
./dev.sh               # infra + FastAPI backend (:8000) + Next.js frontend (:3000)
```

or just the backend:

```bash
cd packages/ui/backend
PYTHONPATH=../../data-layer/src:../../agents/src:src \
  ../../.venv/bin/uvicorn monitor_ui.main:app --app-dir src --host 0.0.0.0 --port 8000
curl http://localhost:8000/api/health
```

## 8. Seed a world and play

Browser: open `http://localhost:3000`, sign up, use Quick World (Forge) to
create a universe, then Play.

Headless (needs `MONITOR_AUTH_DISABLED=true`):

```bash
curl -X POST http://localhost:8000/api/forge/quick-world \
  -H 'Content-Type: application/json' \
  -d '{"seed": "A derelict starfreighter drifts near a lonely salvage station.",
       "genre": "sci-fi", "tone": "grim", "name": "The Wreck"}'

uv run python scripts/live_gameplay_smoke.py --turns 3 \
  --benchmark-id narrative_weighted_derelict --output-dir /tmp
```

The smoke script creates its own session in the first universe returned by
`GET /api/universes/universes`, plays N scripted player turns, and writes a
markdown transcript.

> **Warning.** `scripts/seed_world_quick.py` starts with `DETACH DELETE` on the
> whole Neo4j database. Do not run it on a database that holds anything you
> care about — prefer Quick World through the API as above.

## Troubleshooting

| Symptom | Cause / fix |
|---------|-------------|
| `no active model_pair is registered` | step 5 — run `sync_pair_from_defaults.py` |
| `ensure_collection` dimension guard fails | `EMBEDDING_DIMENSION`/pair/collections disagree — fix `.env`, re-run step 5.3 |
| Backend up but API says `Not authenticated` | `MONITOR_AUTH_DISABLED` is `false`; either log in or set it `true` locally and restart the backend |
| Provider test 401 from Z.AI | the stored tokens are expired — use another tier row |
| GLiNER container restarts | `docker logs monitor-gliner`; needs the rebuilt image (backbone baked in) |
| First `uvicorn` start takes ~60 s | heavy imports; watch the log, then `/api/health` |
