# Playwright for LLM Roleplay — Testing the Live Play UI

> **Status**: design draft — implement alongside the existing `scripts/e2e_full_loop.py` harness.
> **Audience**: anyone touching `packages/ui/frontend/`, the GM pipeline, or the
> `InstructablePlayer` driver.
> **Companions**: `docs/testing/HARNESS_FULL_LOOP.md` (LLM-to-LLM harness),
> `docs/testing/REPLAYS.md` (replay corpus), `packages/agents/src/monitor_agents/players/`
> (test-player abstraction).

## 1. The problem

`scripts/e2e_full_loop.py` already proves the **loop** runs end-to-end — real
character creation, real `bootstrap_story_scene`, real `SceneLoop`, real Ollama.
What it does not prove is that the **Play UI** keeps up with that loop:

* the WebSocket protocol renders correctly into bubbles (`.msg-gm`, `.msg-player`);
* the streaming state machine (`start` → `composing` → `token` → `done`) animates
  without flicker, loss, or re-ordering;
* `thinking` / `thinking_end` and `tool_call` / `tool_result` show up in the
  right places and collapse correctly;
* dice prompts (`dice_request`), failure cards, and the `End scene` → `Wrap up`
  transition are wired to the right mutations;
* phase chips reflect backend transitions (`awaiting_character` →
  `session_zero` → `char_creation` → `active_play` → `scene_ended`).

Hermetic CI cannot prove this; it needs a real browser against a real backend
talking to real models. Playwright is the right tool because we get
**deterministic DOM assertions + a real browser engine + trace/video artifacts**
on every run.

## 2. The shape

Three concentric layers, each opt-in so the default CI stays fast:

| Layer | What it proves | Trigger | Time budget | Status |
| ----- | -------------- | ------- | ----------- | ------ |
| L1 Page smokes | Every route mounts without throwing. | every PR | < 2 min total | **shipped** (`e2e/pages.spec.ts`) |
| L2 Interaction flows | Setup form → first turn → GM narrates. | nightly | 1–3 min | **shipped** (`e2e/play-flow.spec.ts`, opt-in via `E2E_INTERACTION=1`) |
| L3 **LLM roleplay** | Full multi-turn session: setup → IC dialogue → dice (if any) → OOC detour → recap → wrap-up. Phase events + bubble diff match a live backend transcript. | manual / nightly / on-demand | 3–15 min | **designed here** |

L3 lives next to L1/L2 under `packages/ui/frontend/e2e/`. It is **opt-in** via
`E2E_ROLEPLAY=1` so PR CI doesn't burn ten minutes on a real Ollama run; nightly
and on-demand pipelines flip it on.

## 3. Why a separate spec, not a bigger `play-flow.spec.ts`?

The existing interaction spec has one job: prove a single turn streams to the
page. L3 is **conversation-shaped**, not turn-shaped:

* it asserts **across** turns (turn-N+1 sees turn-N's effects);
* it owns its own **transcript capture** so a flake can be diffed against the
  live backend (`tests/e2e/logs/roleplay/`);
* it depends on **seeds + service health** that page smokes don't need;
* it intentionally **watches the backend log** so a UI success with a silent
  Narrator fallback is still caught (the matrix in §6).

Keeping it separate also lets us pin **timeout budgets per spec file** —
`test.setTimeout(900_000)` on L3 without slowing L1.

## 4. Configuration (extension to `playwright.config.ts`)

```ts
// packages/ui/frontend/playwright.config.ts (additions only — keep the
// existing projects intact so PR CI behavior is unchanged).
import { defineConfig, devices } from "@playwright/test";

const ROLEPLAY = process.env.E2E_ROLEPLAY === "1";

export default defineConfig({
  // ...existing config...
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    // Nightly / on-demand — requires the full stack and Ollama.
    ...(ROLEPLAY
      ? [{
          name: "roleplay",
          use: {
            ...devices["Desktop Chrome"],
            baseURL: process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3100",
            trace: "on",
            video: "retain-on-failure",
            screenshot: "only-on-failure",
            // Slow-motion knob so timing flakes are reproducible.
            launchOptions: process.env.PW_SLOWMO
              ? { slowMo: Number(process.env.PW_SLOWMO) }
              : undefined,
          },
          testMatch: /roleplay\.spec\.ts$/,
          timeout: 900_000,
          expect: { timeout: 15_000 },
        }]
      : []),
  ],
});
```

Why `trace: "on"` and `video: "retain-on-failure"`: L3 will pass-or-fail on a
per-turn basis, and the trace zip is the single artifact an investigator needs
to see DOM state, network, and console in one place.

## 5. Selectors — the test-anchor contract

Already shipped in the Play UI (no new `data-testid` needed for the baseline):

| Surface | Selector | Notes |
| ------- | -------- | ----- |
| New-session CTA | `getByRole("button", { name: /new play session/i })` | Already on the empty state. |
| Setup form selects | `.glass.rounded-2xl select` (indexes 0..3) or `#setup-rules-system`, `#setup-controlled-pc`, `#setup-persona`, `#setup-story-premise` | Multiverse, Universe, System, Controlled-PC, in DOM order. |
| Create-session | `getByRole("button", { name: /create session/i })` | Disabled until `selectedUniverseId`. |
| Composer textarea | `textarea:visible` (first) | |
| Composer send | `getByRole("button", { name: /send message/i })` | `aria-label="Send message"` on `Composer.tsx`. |
| GM bubbles | `.msg-gm` | Already in `play-flow.spec.ts`. |
| Player bubbles | `.msg-player` | Same DOM contract. |
| System chips | `.msg-system` | |
| Thinking trace toggle | `[aria-label="Collapse reasoning" i], [aria-label="Expand reasoning" i]` | |
| Tool call card | `[data-tool-call-id]` *(proposed — see §10)* | Currently rendered by `ToolCallCard` with no anchor; a `data-tool-call-id` is the smallest test-stable hook. |
| Dice prompt | `getByRole("button", { name: /roll/i })` + `[data-dice-spec]` *(proposed)* | `DiceRollPrompt` is the host. |
| Failure card | `.rounded-xl.border-red-500\\/25` | |
| Typing indicator | `[aria-label="GM is typing"]` *(proposed — see §10)* | `TypingIndicator.tsx` currently has no a11y hook. |
| End scene | `getByRole("button", { name: /end scene/i })` | |
| Recap modal | `[role="dialog"][aria-label*="recap" i]` *(proposed)* | `RecapModal.tsx` exists; we need an explicit `aria-label`. |
| Phase chip | text match (`/awaiting character/i`, `/in play/i`, `/scene ended/i`) | `PhaseChip` styles per phase, label text is the contract. |
| WS status pill | `[data-ws-status="connected" i], [data-ws-status="reconnecting" i], [data-ws-status="disconnected" i]` *(proposed)* | `StatusPill` is rendered by `Composer`; expose `data-ws-status`. |

The "(proposed)" items are the minimal additions the design needs; §10 lists them
as a small follow-up. Tests should be authored to **fail loudly** if any of
them regress, with clear error messages pointing at the selector.

## 6. The scenario matrix

L3 runs the same scenarios `scripts/e2e_full_loop_scenarios.py` exposes, but
through the Play UI rather than the harness. Two reasons this is worth doing
even though the harness already exists:

* the harness exercises the **backend**; L3 exercises the **rendering** of
  that backend's output, including the WS state machine;
* failures are easier to attribute — a Playwright diff points at a missing CSS
  class or a stale React key; a harness log points at the loop.

| ID | System | Scenario | Tone | Mode | Style | Expected min turns |
| -- | ------ | -------- | ---- | ---- | ----- | ------------------ |
| R-01 | VtM | `vtm_primogen` | dramatic | autonomous_gm | dice_game_system | 3 IC + 1 OOC + wrap |
| R-02 | VtM | `vtm_embrace` | horror | autonomous_gm | narrative | 3 IC + 1 OOC + wrap |
| R-03 | DiS | `dis_salvage` | grim | autonomous_gm | dice_game_system | 3 IC (zero-G, alarm) + wrap |
| R-04 | DiS | `dis_void_whisper` | mystery | gm_assistant | narrative | 2 IC + 1 OOC + wrap |

Run R-01 first; gate R-02..R-04 on it passing.

## 7. The fixture: bridging Playwright and `InstructablePlayer`

`InstructablePlayer` lives in the **backend** (Python). L3 needs the same
concept on the **browser side**: a deterministic or LLM-backed player that
sends messages through the Play UI as if it were a human at the keyboard.

Two-tier strategy:

1. **Scripted tier** (default, fast, deterministic):
   `tests/e2e/fixtures/playwright-driver.ts` exports `sendScripted(page, lines)`.
   Each line is `{ text, intent? }`; the driver types into the textarea and
   presses Enter. Asserts that the player bubble appears within `expect(2_000)`.
   Use this for CI smoke (R-01 only).

2. **LLM tier** (nightly/on-demand):
   `tests/e2e/fixtures/llm-driver.ts` runs an `ollama` call **server-side**
   (not in the browser — it would block the event loop) and pipes the
   resulting text into the same Composer through a thin Node WS client. The
   browser never talks to Ollama directly. Same driver contract as
   `InstructablePlayer.InstructedSpec`. Falls back to a canned line on
   timeout/empty/error.

Why server-side: the existing `InstructablePlayer` already runs through
litellm in Python. Re-using it avoids duplicating the LLM plumbing — a
**subprocess bridge** (`tests/e2e/fixtures/llm-bridge.py`) takes a JSON
sequence of GM bubbles on stdin and writes the player's next turn on stdout.
This is the same `InstructedSpec` config, the same `model_pairs`, the same
retries.

```
┌────────────────────────┐   WS    ┌─────────────────────────┐
│ Play UI (Chromium)     │ ◀─────▶ │ ui-backend              │
└────────────────────────┘         │  (FastAPI + WS)         │
        ▲                          └─────────────────────────┘
        │ Playwright                         ▲
        ▼                                    │ REST + WS
┌────────────────────────┐  stdio   ┌─────────┴───────────────┐
│ Node test runner       │ ◀──────▶ │ llm-bridge.py           │
│  (scripted or LLM      │          │  re-uses InstructablePlayer
│   via subprocess)      │          │  + litellm + Ollama     │
└────────────────────────┘          └─────────────────────────┘
```

## 8. The spec, end-to-end

```ts
// packages/ui/frontend/e2e/roleplay.spec.ts
import { expect, test } from "@playwright/test";
import { sendScripted } from "./fixtures/playwright-driver";
import { attachWsSpy } from "./fixtures/ws-spy";

test.describe("roleplay (live LLM-backed)", () => {
  test.skip(!process.env.E2E_ROLEPLAY, "set E2E_ROLEPLAY=1 to enable");
  test.setTimeout(900_000);

  test("R-01 VtM Primogen — three IC turns then recap", async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(String(e)));

    // 1. Capture WS frames for the matrix in §6.
    const ws = await attachWsSpy(page);

    // 2. Bootstrap: setup form → create session.
    await page.goto("/play", { waitUntil: "networkidle" });
    await page.getByRole("button", { name: /new play session/i }).click();

    const setup = page.locator(".glass.rounded-2xl select");
    await setup.nth(0).waitFor({ timeout: 20_000 });
    // Multiverse (0), Universe (1), System (2), Controlled-PC (3).
    for (const idx of [0, 1, 2]) {
      const opt = await setup.nth(idx).locator("option[value]:not([value=''])").first();
      await setup.nth(idx).selectOption(await opt.getAttribute("value") ?? "");
    }

    // Persona is optional; leave Controlled-PC empty to drive Session Zero.
    await page.locator("#setup-story-premise").fill(
      "I am the youngest Primogen. The Prince just named my sire."
    );

    await page.getByRole("button", { name: /create session/i }).click();

    // 3. Wait for the Composer to mount (WS only opens after create).
    const composer = page.locator("textarea:visible").first();
    await composer.waitFor({ timeout: 30_000 });
    await expect(page.locator("[data-ws-status]")).toHaveAttribute(
      "data-ws-status", "connected", { timeout: 15_000 }
    );

    // 4. Drive three scripted IC turns. Each:
    //    a) fill + Enter
    //    b) wait for a new .msg-gm
    //    c) assert content length, no fallback, no error toast.
    const lines = [
      "I take my seat at the back of the chamber.",
      "I meet the Prince's gaze and ask him to repeat my sire's name.",
      "I nod slowly and keep my silence.",
    ];
    for (const text of lines) {
      const before = await page.locator(".msg-gm").count();
      await sendScripted(page, text);
      await expect
        .poll(async () => page.locator(".msg-gm").count(), { timeout: 120_000 })
        .toBeGreaterThan(before);
      const last = page.locator(".msg-gm").last();
      await expect(last).toContainText(/[\S]/, { timeout: 5_000 });
      await expect(last).not.toContainText(/turn (timed out|errored)/i);
    }

    // 5. One OOC detour to prove the (( ... )) routing works.
    const beforeOoc = await page.locator(".msg-gm").count();
    await composer.fill("(( Oracle: is my sire's name really Sasha? ))");
    await composer.press("Enter");
    await expect
      .poll(async () => page.locator(".msg-gm").count(), { timeout: 60_000 })
      .toBeGreaterThan(beforeOoc);

    // 6. End scene + assert wrap-up modal appears.
    await page.getByRole("button", { name: /end scene/i }).click();
    await expect(page.locator("[role='dialog']")).toBeVisible({ timeout: 30_000 });

    // 7. WS matrix: every turn produced start+token+done; no error frames.
    const matrix = ws.matrix();
    for (const turn of matrix) {
      expect(turn.events, `turn ${turn.id} missing events`).toEqual(
        expect.arrayContaining(["start", "token", "done"]),
      );
      expect(turn.events, `turn ${turn.id} had error frame`).not.toContain("error");
    }
    expect(errors, `client errors: ${errors.join("; ")}`).toEqual([]);
  });
});
```

The other R-02..R-04 specs follow the same shape; the matrix is the only thing
that changes.

## 9. The fixtures

`tests/e2e/fixtures/playwright-driver.ts`:

```ts
import type { Page } from "@playwright/test";

export async function sendScripted(page: Page, text: string) {
  const ta = page.locator("textarea:visible").first();
  await ta.fill(text);
  await ta.press("Enter");
}
```

`tests/e2e/fixtures/ws-spy.ts` (browser-side frame capture):

```ts
import type { Page } from "@playwright/test";

/**
 * Attach a WebSocket spy that records every frame sent/received on
 * `/api/chat/ws/<session>`. Returns a handle with `matrix()` that
 * groups events by `message_id`.
 *
 * Why a fixture and not a per-spec snippet: the page opens the socket
 * inside a React effect on mount, so the spy has to install a
 * `addInitScript` before navigation. Doing this once via `test.use(...)`
 * keeps each spec readable.
 */
export async function attachWsSpy(page: Page) {
  await page.addInitScript(() => {
    const W = window as unknown as { __wsSpy?: unknown };
    W.__wsSpy = {
      frames: [] as Array<{ dir: "send" | "recv"; t: number; data: unknown }>,
    };
    const OrigWS = window.WebSocket;
    // @ts-expect-error - intentional subclass
    window.WebSocket = class extends OrigWS {
      constructor(url: string | URL, protocols?: string | string[]) {
        super(url, protocols);
        const sock = this;
        const origSend = sock.send.bind(sock);
        sock.send = (data: string | ArrayBufferLike | Blob | ArrayBufferView) => {
          (W.__wsSpy as { frames: Array<{ dir: "send" | "recv"; t: number; data: unknown }> }).frames.push({
            dir: "send", t: Date.now(), data: safeParse(data),
          });
          return origSend(data);
        };
        sock.addEventListener("message", (ev: MessageEvent) => {
          (W.__wsSpy as { frames: Array<{ dir: "send" | "recv"; t: number; data: unknown }> }).frames.push({
            dir: "recv", t: Date.now(), data: safeParse(ev.data),
          });
        });
      }
    };
    function safeParse(d: unknown) {
      if (typeof d !== "string") return d;
      try { return JSON.parse(d); } catch { return d; }
    }
  });
  return {
    matrix() {
      return page.evaluate(() => {
        const frames = (window as unknown as { __wsSpy: { frames: unknown[] } }).__wsSpy.frames;
        const byMsg = new Map<string, { id: string; events: string[] }>();
        for (const f of frames as Array<{ dir: string; data: { type?: string; message_id?: string } }>) {
          if (f.dir !== "recv") continue;
          const id = f.data?.message_id ?? "_global";
          const ev = byMsg.get(id) ?? { id, events: [] };
          if (f.data?.type) ev.events.push(f.data.type);
          byMsg.set(id, ev);
        }
        return [...byMsg.values()];
      });
    },
  };
}
```

`tests/e2e/fixtures/llm-bridge.py` — re-uses `InstructablePlayer`:

```python
"""LLM-backed Playwright driver.

Reads GM-bubble JSON on stdin (one object per line:
  {"role": "gm", "content": "...", "intent": "..."}
), writes the next player turn on stdout
  {"text": "...", "intent": "..."}

Same configuration surface as InstructedSpec so the test runner can pass
the same model / temperature / max_tokens the harness uses.

Re-uses In structablePlayer so behavior matches scripts/e2e_full_loop.py
— same fallback, same retries, same model name.
"""
```

## 10. The minimal product changes this design requires

Three tiny additions to the Play UI so tests have stable hooks:

1. `ToolCallCard.tsx` — add `data-tool-call-id={call.id}` to the root element.
2. `TypingIndicator.tsx` — add `aria-label="GM is typing"` to the root element.
3. `StatusPill.tsx` — add `data-ws-status={status}` on the root element.
4. `RecapModal.tsx` — add `role="dialog" aria-label="Scene recap"` on the root.
5. `DiceRollPrompt.tsx` — add `data-dice-spec={request.spec}` on the root.

None change behavior; all five are 1–3 line patches. Land them in a single
"roleplay testability" PR before flipping `E2E_ROLEPLAY=1` in nightly.

## 11. CI wiring

`.github/workflows/nightly.yml` (or the existing nightly equivalent):

```yaml
- name: Roleplay L3 (live LLM)
  env:
    E2E_ROLEPLAY: "1"
    NEXT_PUBLIC_API_URL: http://localhost:8000
    MONITOR_PLAYTEST_MODEL: ollama/qwen2.5:latest
  run: |
    docker compose -f infra/docker-compose.yml up -d
    python scripts/seed_light_role_default.py
    python scripts/seed_llm_providers.py
    cd packages/ui/frontend && npx playwright test --project=roleplay
```

On PR CI: `E2E_ROLEPLAY` is unset, so the roleplay project is excluded; L1/L2
run as today. On nightly / manual dispatch: full stack + L3 runs in 5–10 min.

## 12. Why this design, not a different shape

* **Why Playwright, not Vitest + RTL** — we need a real browser engine
  (react-virtuoso virtualization, WebSocket lifecycle, framer-motion
  animations). RTL on `happy-dom` would paper over half the bugs we care
  about.
* **Why not Cypress** — Playwright already ships in the repo with trace/video
  artifacts; consolidating on one tool keeps CI fast.
* **Why re-use `InstructablePlayer`, not a fresh driver** — project memory
  explicitly calls out "Hermetic ≠ runtime" — only a real LLM call proves
  the loop actually completes. Re-using the same driver guarantees parity
  with the harness; if a regression hits the harness, this spec catches it
  in the UI and vice-versa.
* **Why opt-in via env, not a separate workflow** — keeps the test surface
  close to the existing CI runs so anyone touching `e2e/` sees the whole
  picture. A separate workflow hides the relationship.

## 13. Open follow-ups

* Decide whether the LLM tier ships in v1 or waits for the testability
  patches. Recommended: ship the **scripted tier** + testability patches
  in the same PR; LLM tier is a follow-up.
* Add `tests/e2e/logs/roleplay/` retention policy (currently unbounded).
* Visual regression on `.msg-gm` / `.msg-player` via Playwright `toHaveScreenshot`
  once the UI stabilizes.