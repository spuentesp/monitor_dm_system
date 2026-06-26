# Forge Replay

- **API**: `http://localhost:8000/api`
- **Generated at**: `2026-06-26T00:32:31.043738+00:00`

## Surface coverage

| Surface | OK | Latency | Summary |
|---|---|---|---|
| `GET /health` | ✅ | 0.01s | ok |
| `POST /forge/quick-world` | ✅ | 1.03s | universe_id=394bdc96-53d6-44d5-a049-3dfca27f32f8 |
| `POST /forge/demo-world` | ✅ | 0.33s | universe_id=069c4689-ec41-450d-b059-f66d1ce37fb0 |
| `GET /universes/universes` | ✅ | 0.12s | count=200, first=394bdc96-53d6-44d5-a049-3dfca27f32f8 |
| `POST /chat (existing-universe bootstrap)` | ✅ | 0.1s | session_id=a8fa3f2c-45b1-43dc-acfb-1727da62254e |
| `GET /universes/universes/{id}` | ✅ | 0.01s | entities=0 |
| `GET /chat/{sid}/state` | ✅ | 0.0s | phase=awaiting_character, turns=? |
| `GET /chat/{sid}/recap (CF-2)` | ✅ | 15.53s | chars=215 |
| `GET /graph/world` | ✅ | 0.35s | ok |
| `GET /ingest/packs` | ✅ | 0.18s | count=30 |