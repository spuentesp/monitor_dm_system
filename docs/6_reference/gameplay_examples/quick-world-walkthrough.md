# Quick World: seed → playable in under two minutes

> The Emochi/SillyTavern-style on-ramp. You don't need a rulebook to start —
> a sentence is enough. See `docs/FORGE_INGESTION_PLAN.md` §B for the design.

## UI flow

1. **World Forge** → the dashboard opens on the **Quick Start** tab.
2. Type a seed in one or two sentences, e.g.
   *"A rain-soaked harbor city where the drowned barter for the memories they
   lost at sea."* (or click one of the example chips).
3. Optionally pick a **genre** and **tone** chip, and a **world name**. Leave
   "Start a session immediately" checked.
4. **Forge world.** In ~30–80s MONITOR returns a result card: the world name +
   premise, its **axiom** (the load-bearing world-truth), the **entities** it
   committed to canon (allies, antagonists, a location, sometimes a faction —
   each with a *want*), the **opening scene**, and a **suggested character**.
5. Click **Play here now** → you land in the Play console on a session already
   bound to the new universe. Type your first action; the GM narrates using the
   generated NPCs and places. Or **Open in tree** to browse the world in Worlds.

The forged world also becomes your **active world** (sidebar picker), so Play,
GM Assistant, and the Worlds tree all default to it afterward.

## API flow (scriptable)

```bash
curl -s -X POST localhost:8001/api/forge/quick-world \
  -H 'content-type: application/json' \
  -d '{
        "seed": "A frontier mining moon where the ore whispers and the company owns your air.",
        "genre": "sci-fi western",
        "tone": "grim",
        "start_playing": true
      }'
```

Returns `multiverse_id`, `universe_id`, `world_name`, `axiom`, `entities[]`
(name/type/description/want/tags), `lore_facts[]`, `opening_scene`,
`pc_concept`, `committed`, `errors`, and `session_id` (when `start_playing`).

Then narrate turn one:

```bash
curl -s -X POST localhost:8001/api/chat/<session_id>/send \
  -H 'content-type: application/json' \
  -d '{"content":"I am Cole Mara, an air-debt drifter. I push into Shaft 7 looking for Nadia Voss."}'
```

A verified run: the seed above produced **The Dust Margin** — 5 canon entities
(Nadia Voss, Superintendent Craine, Shaft 7, the Dust Margin Union, …), 1
axiom, 3 lore facts, 8 commits / 0 errors — and the bound session narrated the
descent into Shaft 7 referencing the generated NPC and location.

## How it differs from Lorebook Ingestion

| | Quick Start | Lorebook Ingestion |
|---|---|---|
| Input | one-sentence seed | PDF / docx / epub / md |
| Time | ~30–80s | minutes (multi-pass) |
| Output | small playable world (canon) | full knowledge pack (review queue) |
| Best for | "I have a vibe, let's play" | "I have a 300-page setting book" |

Both land in the same place: a bound, playable universe.
