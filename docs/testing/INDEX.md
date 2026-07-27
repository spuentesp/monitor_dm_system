---
description: "Index for MONITOR test-tier docs. One question per file."
tags: [index, testing]
layer: 0
---

# Test tiers

Two tiers, two files:

| Tier | What it exercises | File |
|---|---|---|
| **In-process full-loop** | Real character + sheet → `bootstrap_story_scene` → real `SceneLoop`, driven by `InstructablePlayer`. No HTTP. | [HARNESS_FULL_LOOP.md](./HARNESS_FULL_LOOP.md) |
| **Full-stack replay suite** | The running backend over HTTP, seven surfaces (forge + copilot + long-form + …). | [REPLAYS.md](./REPLAYS.md) |

If a change touches the loop *in-process*, run the harness. If it touches
the live backend over HTTP, run the replays. The two tiers answer
different questions — neither subsumes the other.
