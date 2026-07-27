---
description: "In-process full-loop harness — real character + real scene + real GM pipeline."
tags: [testing, e2e, harness]
layer: 0
---

# In-process full-loop harness

One script: `scripts/e2e_full_loop.py`. Real character + sheet → real
story + scene bootstrap → real `SceneLoop` driven by `InstructablePlayer`.
No FastAPI, no HTTP. The character is synthesized from the scenario's
`character_spec` + the game-system's attribute defaults (same pattern
`scripts/test_dis_session.py` uses), persisted via
`neo4j_create_entity` + `mongodb_create_character_sheet`.

## Why this script exists

The prior generation of harnesses (`e2e_gm_authority_fake_user.py` and
`e2e_llm_vs_llm.py`) fabricated `scene_id` and `game_context` by hand
and called `SceneLoop.run()` directly. With the narration-pipeline fix,
`mongodb_append_turn` started rejecting every fabricated UUID with
"Scene {uuid} not found" — those harnesses had *always* been broken, the
rejection just made the bug loud.

This script fixes the root cause: every character, story, scene, and
sheet goes through the canonical creation paths. No fabricated UUIDs
anywhere.

## Data flow

```
Scenario (scripts/e2e_full_loop_scenarios.py)
    ↓ character_spec + world_id
build_session(system_id, universe_id)   # loads game_systems doc
    ↓
synthesize_character(character_spec + system.attributes defaults)
                                OR  ← --character-driver {scripted,llm,skip}
CharacterCreationLoop.start() + .process_player_input(player.next())
    ↓
neo4j_create_entity(EntityCreate(...))   # real Entity
mongodb_create_character_sheet(...)      # real CharacterSheet
    ↓
bootstrap_story_scene(session_dict)      # real Story + Scene in Neo4j + Mongo
    ↓
SceneLoop(scene_id=<real>, story_id=<real>, universe_id=<real>, ...)
    ↓ for --turns-per-scene turns per scene, --scenes N total:
InstructablePlayer.next()  →  SceneLoop.run(player_text)
    ↓ (between scenes)
next_scene_in_story() → bootstrap_story_scene(session)  # new scene, same story_id
    ↓
{turns_count, narrative_text} → persisted to MongoDB scenes.turns[]
```

## World creation (`--create-world`)

By default the harness picks the **first existing** `Universe` node.
With `--create-world`, it creates a **fresh** Universe under the first
seeded `Multiverse` via `neo4j_create_universe(...)`:

```
--create-world --world-name "Awakening in Seattle"
```

The new universe is bound to `default_game_system_id=V5_SYSTEM_ID` (or
the matching DiS id) so the auto-bound game system follows the story
without a separate wiring step.

## Character creation dialog (`--character-driver`)

The harness drives `CharacterCreationLoop` step-by-step, with the
player answering each `step_prompt` via an `InstructablePlayer`:

| `--character-driver` | Player | Cost |
|---|---|---|
| `scripted` (default) | `ScriptedSpec` with 6 canned answers per scenario | 0 LLM calls |
| `llm` | `InstructedSpec` — real litellm call, GM prompt → answer | ~1 LLM call per step |
| `skip` | bypasses the loop; synthesizes from `character_spec` | 0 LLM calls |

The full per-step transcript (GM prompt + player answer per step)
appears in the final markdown under the `Phase B — character creation`
section. Use `scripted` for fast hermetic runs; use `llm` to prove the
loop handles real player voice.

## Multi-scene stories (`--scenes N`)

Each scene gets a **fresh `scene_id`** but shares the **same
`story_id`** with the prior scene. The harness:

1. Mints scene 1 via `bootstrap_story_scene(session_dict)`.
2. Runs `SceneLoop.run(player_text)` for `--turns-per-scene` turns.
3. Before minting scene N+1, calls `bootstrap_story_scene(session_dict)`
   with the existing `story_id` set — the helper sees the guard
   `if not story_id` and skips creation, then enters the
   `if not scene_id and story_id` branch to mint just the new scene.
4. The new scene inherits the same `actor_id` and `actor_context`.

Verification (live run on VtM):

```
Scenes after running --scenes 3: 3 distinct scene_ids, all sharing
one story_id b9b4ad63-1ca8-4ead-a0ea-910d104a9d37. Each scene has
the expected number of user+gm turns alternating.
```

## Resume an existing story (`--resume-from-story-id <uuid>`)

```
--resume-from-story-id b9b4ad63-1ca8-4ead-a0ea-910d104a9d37 \
--scenes 1 --turns-per-scene 4
```

Skips Phase A (world) + Phase B (character creation). The harness:

1. Loads the story from Neo4j by id; checks it exists.
2. Picks up the most recent character sheet for the universe to
   rehydrate `actor_context`.
3. Calls `bootstrap_story_scene(session_dict)` with `session["story_id"]`
   pre-populated — the helper is **idempotent** in this state and
   simply mints a fresh scene under the existing story.
4. Runs the new scene loop the same way as the new-story path.

After resume, the story has **one more scene** than before; all share
the same `story_id` and `universe_id`.

## Quick start

```bash
# Bring up the infra + source env as usual.
set -a; source .env; set +a
export MONITOR_PLAYTEST_MODEL=ollama/qwen2.5:latest
export RETRIEVAL_EMBEDDING_MODEL=ollama/nomic-embed-text

# Hermetic smoke test (no LLM called — scripted player).
python scripts/e2e_full_loop.py --mock-llm --system dis --scenario dis_salvage --turns 3

# Live DiS run with real Ollama chat model.
python scripts/e2e_full_loop.py --system dis --scenario dis_salvage --turns 6

# Live VtM run.
python scripts/e2e_full_loop.py --system vtm --scenario vtm_primogen --turns 6
```

Outputs land in `tests/e2e/logs/full_loop/<scenario>_<UTC>.{md,json}`.

## CLI flags

```
--scenario           vtm_primogen | vtm_embrace | dis_salvage | dis_void_whisper
--system            vtm | dis
--universe-id       <uuid>            # override default (first existing)
--create-world                       # create fresh Universe instead of pick
--world-name        <str>            # name for new universe (auto if absent)
--character-driver  scripted | llm | skip   # default scripted
--scenes            N                # total scenes under one story (default 1)
--turns-per-scene   N                # legacy alias: --turns
--timeout           seconds          # per-turn hard cap (default 300)
--mock-llm                            # swap InstructedSpec for ScriptedSpec
--player-model      litellm-string   # default $MONITOR_PLAYTEST_MODEL
--resume-from-story-id <uuid>        # skip world+char-creation, add scene
--output-dir        path             # default tests/e2e/logs/full_loop
```

## Combinations

| Goal | CLI |
|---|---|
| Hermetic smoke (single scene, scripted char dialog, scripted player) | `--character-driver scripted --mock-llm --turns-per-scene 2` |
| Live VtM end-to-end (new world + char creation + 3 scenes) | `--system vtm --create-world --world-name "..." --character-driver scripted --scenes 3 --turns-per-scene 4` |
| Live VtM with real LLM character dialog | add `--character-driver llm` |
| Resume an existing story with 1 new scene | `--resume-from-story-id <uuid> --scenes 1 --turns-per-scene 4` |
| Quick smoke (skip char-creation, mock player) | `--character-driver skip --mock-llm --turns-per-scene 2` |

## Hermetic pytest coverage

`tests/e2e/test_e2e_full_loop.py` (RUN_E2E=1). Verifies:
- all scenarios load + resolve system IDs,
- the scripted player serves scripted lines then falls back,
- the observation buffer is bounded,
- the source label maps spec class → transcript column.

These tests do **not** prove the pipeline works end-to-end. They prove
the harness shape is right. Live verification is the separate gate.

## Live verification gate

Hermetic suites passing ≠ the loop is healthy. After any change to
`SceneLoop`, `bootstrap_story_scene`, `CharacterCreationLoop`, or the
GM pipeline, run **both**:

```bash
python scripts/e2e_full_loop.py --system dis --scenario dis_salvage --turns 6
python scripts/e2e_full_loop.py --system vtm --scenario vtm_primogen --turns 6
```

Acceptance signals in each transcript:
- `fallback turns: 0`
- no `Scene {…} not found` line in the run log
- `narrative_text` present in every turn
- `resource_deltas` populated when the action warrants it

A single fallback turn is acceptable as long as the surrounding turns
are real runs and the JSON's `fallback_turns` field is small.

## Why two specs?

`InstructablePlayer` accepts a `PlayerSpec`. The harness wires two:

| Spec | Mode | Purpose |
|---|---|---|
| `ScriptedSpec` | `--mock-llm` | Hermetic CI / smoke tests. |
| `InstructedSpec` | default | Live verification. Scripted-opens + litellm with graceful fallback. |

Both speak to `SceneLoop` through `InstructablePlayer.next()` only —
the harness never imports litellm directly. That separation keeps test
fixtures deterministic while production paths stay LLM-native.
