import { expect, test } from "@playwright/test";

/**
 * Interaction flow (T-081 / plan T-065): create a session through the real
 * setup form, send a turn, and require freshly streamed GM narration.
 *
 * Opt-in: needs the full backend stack with a configured LLM and takes
 * 30-90s per turn, so it only runs with E2E_INTERACTION=1 (nightly), keeping
 * the default page smokes fast.
 */
test.describe("play interaction", () => {
  test.skip(process.env.E2E_INTERACTION !== "1", "set E2E_INTERACTION=1 to run");

  test("create session → send turn → GM narrates", async ({ page }) => {
    test.setTimeout(240_000);
    const errors: string[] = [];
    page.on("pageerror", (err) => errors.push(String(err)));

    await page.goto("/play", { waitUntil: "networkidle" });
    await page.getByRole("button", { name: /start new session/i }).first().click();

    // Setup-panel selects in DOM order: multiverse, universe, system, PC.
    const selects = page.locator(".glass.rounded-2xl select");
    await selects.first().waitFor({ timeout: 20_000 });

    const pickFirstReal = async (idx: number) => {
      const options = await selects.nth(idx).locator("option").all();
      for (const opt of options) {
        const value = await opt.getAttribute("value");
        if (value) {
          await selects.nth(idx).selectOption(value);
          return true;
        }
      }
      return false;
    };

    test.skip(!(await pickFirstReal(0)), "no multiverse seeded");
    await page.waitForTimeout(1000); // universes load for the chosen setting
    test.skip(!(await pickFirstReal(1)), "no universe in the first setting");

    const createBtn = page.getByRole("button", { name: /create session/i });
    await expect(createBtn).toBeEnabled({ timeout: 15_000 });
    await createBtn.click();

    const input = page.locator("textarea:visible").first();
    await input.waitFor({ timeout: 30_000 });
    const before = await page.locator(".msg-gm").count();

    await input.fill("Roll me a quick character and open the scene.");
    await input.press("Enter");

    // Strict: a NEW GM bubble exists and carries substantial prose.
    await page.waitForFunction(
      (n) => {
        const els = [...document.querySelectorAll(".msg-gm")];
        return els.length > n && (els[els.length - 1].textContent || "").length > 150;
      },
      before,
      { timeout: 180_000 },
    );

    expect(errors, `client errors: ${errors.join("; ")}`).toEqual([]);
  });
});
