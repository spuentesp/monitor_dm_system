---
description: "Full-stack live-narration / GM-assistant replay suite."
tags: [testing, e2e, replays]
layer: 0
---

# Full-stack replay suite

> **The running backend over HTTP, six surfaces.** One entry point
> (`scripts/run_e2e_replays.py`), seven sub-scripts, one combined report.

For the in-process loop harness (real character + real scene + real
`SceneLoop`, no HTTP), see [HARNESS_FULL_LOOP.md](./HARNESS_FULL_LOOP.md).

## Quick start

```bash
# 1. Docker stack + UI backend uvicorn at :8000 (usually running already).
docker compose --env-file .env -f infra/docker-compose.yml up -d

# 2. Env.
set -a; source .env; set +a
export MONITOR_PLAYTEST_MODEL=ollama/qwen2.5:latest

# 3. Full suite (~25-30 min wall clock).
python scripts/run_e2e_replays.py

# Subset.
python scripts/run_e2e_replays.py --only forge,copilot
```

The combined report lands at `tests/e2e/logs/replays/replay_run_<UTC>.md`.

## Suites at a glance

| Suite | Script | Wall clock |
|---|---|---|
| `forge` | `scripts/forge_replay.py` | ~25 s |
| `copilot` | `scripts/live_copilot_observe.py` | ~60 s |
| `long_form` | `scripts/long_form_narration.py` | ~12 min |
| `subsystem` | `scripts/subsystem_replay.py` | ~10 min |
| `char_creation` | `scripts/character_creation_replay.py` | ~10 min |
| `session_observe` | `scripts/live_session_observe.py` | ~12 min |

Total full-suite wall clock: **~70 minutes** when the player model is
fast local ollama.

## CLI flags

```
--api-url      http://localhost:8000/api
--only         forge,copilot
--skip         session_observe
--output-dir   tests/e2e/logs/replays
--report       /path/to/custom_report.md
```

## What "passing" means

- Exit `0` — suite completed with no internal assertion failures.
- Exit `1` — at least one internal assertion failed (e.g., a fallback
  marker appeared in GM output, the canonical-universe endpoint
  returned 404).
- Exit `2` — semantic failure the suite can't recover from
  (e.g., char-creation never reached `active_play`).

The entry script treats any non-zero as a failure and writes a
`replay_run_<UTC>.md` with a per-suite pass/fail table.

## Tag reference

`long_form_narration.py` (22 tags): `char_creation_accept`,
`char_creation_stat_roll`, `first_in_fiction_action`, `social_inquiry`,
`lore_recall`, `social_deal`, `exploration_intent`, `first_combat_intent`,
`combat_engaged`, `combat_finisher`, `tactical_assessment`, `deeper_push`,
`puzzle_encounter`, `puzzle_solve`, `puzzle_consequence`, `loot_choice`,
`boss_intro`, `boss_phase_two`, `boss_finisher`, `extraction`,
`extraction_pressure`, `wrap_up`.

`subsystem_replay.py` (14 tags): `intro`, `trust_seed`, `lore_recall`,
`faction_probe`, `social_negotiation`, `npc_voice`, `lore_event`,
`relationship_mirror`, `faction_hook`, `social_deal`, `npc_test`,
`lore_blacksite`, `relationship_close`, `wrap_up`.

`character_creation_replay.py` (10 tags): `intro`, `ask_species`,
`ask_class`, `choose_class`, `roll_stats`, `choose_background`,
`choose_equipment`, `ask_sheet`, `confirm_lock`, `first_action`.
