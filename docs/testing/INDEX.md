---
description: "Index for MONITOR test-tier docs. One question per file."
tags: [index, testing]
layer: 0
---

# Test tiers

Three tiers, three files. L1 and L3 are opt-in; L2 is the always-on default.

| Tier | What it exercises | File |
|---|---|---|
| **L1 — Playwright page smokes** | Every Play UI route mounts without throwing. Fast, no backend required. | `packages/ui/frontend/e2e/{pages,forge-redirects}.spec.ts` |
| **L2 — Full-stack replay suite** | The running backend over HTTP, seven surfaces (forge + copilot + long-form + …). | [REPLAYS.md](./REPLAYS.md) |
| **L3 — Live LLM roleplay** | Real browser + real backend + real Ollama driving a multi-turn session through the Play UI. Opt-in via `E2E_ROLEPLAY=1`. | [PLAYWRIGHT_LLM_ROLEPLAY.md](./PLAYWRIGHT_LLM_ROLEPLAY.md) |
| **In-process full-loop** | Real character + sheet → `bootstrap_story_scene` → real `SceneLoop`, driven by `InstructablePlayer`. No HTTP. | [HARNESS_FULL_LOOP.md](./HARNESS_FULL_LOOP.md) |

If a change touches the loop *in-process*, run the harness. If it touches
the live backend over HTTP, run the replays. If it touches the **Play UI
rendering of the WS stream**, run L3. The three answer different questions
— none subsumes another.
