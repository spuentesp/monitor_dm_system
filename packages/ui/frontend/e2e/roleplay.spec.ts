import { expect, test } from "@playwright/test";
import { sendScripted } from "./fixtures/playwright-driver";
import { attachWsSpy } from "./fixtures/ws-spy";

/**
 * L3 — LLM Roleplay (live backend).
 *
 * Opt-in: requires E2E_ROLEPLAY=1 and a fully-seeded backend (Ollama +
 * Mongo + Neo4j + the ui-backend). The roleplay project in
 * playwright.config.ts only loads this spec when that env is set, so PR
 * CI stays on the L1/L2 path.
 *
 * Each `R-NN` test is a real scenario from scripts/e2e_full_loop_scenarios.py
 * re-driven through the Play UI, so a UI regression and a harness
 * regression surface in the same place.
 *
 * See docs/testing/PLAYWRIGHT_LLM_ROLEPLAY.md for the full design.
 */
test.describe("roleplay (live LLM-backed)", () => {
  test.skip(!process.env.E2E_ROLEPLAY, "set E2E_ROLEPLAY=1 to enable");
  test.setTimeout(900_000);

  test("R-01 VtM Primogen — three IC turns, one OOC detour, wrap up", async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(String(e)));

    const ws = await attachWsSpy(page);

    await page.goto("/play", { waitUntil: "networkidle" });
    await page.getByRole("button", { name: /new play session/i }).click();

    const setup = page.locator(".glass.rounded-2xl select");
    await setup.nth(0).waitFor({ timeout: 20_000 });

    // Multiverse (0) → Universe (1) → System (2). Controlled-PC is left
    // empty so Session Zero drives character creation in chat.
    for (const idx of [0, 1, 2]) {
      const opt = await setup.nth(idx).locator("option[value]:not([value=''])").first();
      const value = await opt.getAttribute("value");
      if (!value) test.skip(true, `setup select #${idx} has no seeded option`);
      await setup.nth(idx).selectOption(value!);
    }

    await page.locator("#setup-story-premise").fill(
      "I am the youngest Primogen. The Prince just named my sire."
    );

    await page.getByRole("button", { name: /create session/i }).click();

    const composer = page.locator("textarea:visible").first();
    await composer.waitFor({ timeout: 30_000 });

    // WS only opens once create-session returns. Wait for it; flake here
    // usually means the backend is unhealthy.
    await expect(page.locator("[data-ws-status]")).toHaveAttribute(
      "data-ws-status",
      "connected",
      { timeout: 15_000 },
    );

    const icLines = [
      "I take my seat at the back of the chamber and look around.",
      "The Prince mentions my sire. I ask him to repeat the name.",
      "I nod slowly and keep my silence.",
    ];

    for (const text of icLines) {
      const before = await page.locator(".msg-gm").count();
      await sendScripted(page, text);
      await expect
        .poll(async () => page.locator(".msg-gm").count(), { timeout: 120_000 })
        .toBeGreaterThan(before);
      const last = page.locator(".msg-gm").last();
      await expect(last).toContainText(/\S/, { timeout: 5_000 });
      // Defends against a silent Narrator fallback (see run_scene() in
      // e2e_full_loop.py: an empty narrative_text still increments the
      // bubble count via the WS `done` event).
      await expect(last).not.toContainText(/turn (timed out|errored)/i);
    }

    // OOC detour via the (( ... )) wrapping convention. The Play UI
    // auto-wraps in OOC mode when no persona is selected; we wrap
    // explicitly here to prove the GM recognizes the marker.
    const beforeOoc = await page.locator(".msg-gm").count();
    await composer.fill("(( Oracle: is my sire's name really Sasha? ))");
    await composer.press("Enter");
    await expect
      .poll(async () => page.locator(".msg-gm").count(), { timeout: 60_000 })
      .toBeGreaterThan(beforeOoc);

    // End scene → wrap-up modal.
    await page.getByRole("button", { name: /end scene/i }).click();
    await expect(page.locator("[role='dialog']")).toBeVisible({ timeout: 30_000 });

    // WS matrix: every per-turn exchange produced the canonical frame
    // triple. A `error` frame anywhere = a failed turn.
    const matrix = ws.matrix();
    for (const turn of matrix) {
      if (turn.id === "_global") continue;
      expect(
        turn.events,
        `turn ${turn.id} missing expected frames`,
      ).toEqual(expect.arrayContaining(["start", "token", "done"]));
      expect(turn.events, `turn ${turn.id} had an error frame`).not.toContain("error");
    }

    expect(errors, `client errors: ${errors.join("; ")}`).toEqual([]);
  });

  test("R-02 VtM Embrace — narrative style, horror tone", async ({ page }) => {
    test.skip(true, "scaffolded; see R-01 for the canonical pattern");
  });

  test("R-03 DiS Salvage — dice_game_system style, grim tone", async ({ page }) => {
    test.skip(true, "scaffolded; see R-01 for the canonical pattern");
  });

  test("R-04 DiS Void Whisper — gm_assistant mode, mystery tone", async ({ page }) => {
    test.skip(true, "scaffolded; see R-01 for the canonical pattern");
  });
});