# Forge Replay

- **API**: `http://localhost:8000/api`
- **Generated at**: `2026-06-26T00:24:03.546771+00:00`

## Surface coverage

| Surface | OK | Latency | Summary |
|---|---|---|---|
| `GET /health` | ✅ | 0.0s | ok |
| `POST /forge/quick-world` | ✅ | 12.68s | universe_id=770a42dd-9843-42cb-a373-fe4653501771 |
| `POST /forge/demo-world` | ✅ | 9.01s | universe_id=069c4689-ec41-450d-b059-f66d1ce37fb0 |
| `GET /universes/universes` | ✅ | 0.13s | count=200, first=e9be67e1-6919-4946-bb64-bca4593ab039 |
| `POST /chat (existing-universe bootstrap)` | ✅ | 0.1s | session_id=cb4a06ce-7f5b-4e77-8112-289b02e34107 |
| `GET /universes/universes/{id}` | ✅ | 0.01s | entities=0 |
| `GET /chat/{sid}/state` | ✅ | 0.0s | phase=awaiting_character, turns=? |
| `GET /chat/{sid}/recap (CF-2)` | ✅ | 5.91s | chars=332 |
| `GET /graph/world` | ✅ | 1.49s | ok |
| `GET /ingest/packs` | ✅ | 0.11s | count=30 |