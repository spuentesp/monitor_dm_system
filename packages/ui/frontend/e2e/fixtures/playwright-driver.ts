import type { Page } from "@playwright/test";

/**
 * Playwright-side driver — fill the Composer textarea and submit with
 * Enter. Waits for the button to be enabled so we never queue an
 * out-of-turn message that the WS would reject.
 *
 * The LLM-backed sibling lives in tests/e2e/fixtures/llm-bridge.py and
 * re-uses InstructablePlayer.InstructedSpec so the LLM-tier tests match
 * the harness exactly.
 */
export async function sendScripted(page: Page, text: string): Promise<void> {
  const ta = page.locator("textarea:visible").first();
  await ta.waitFor({ state: "visible", timeout: 15_000 });
  await ta.fill(text);

  const send = page.getByRole("button", { name: /send message/i });
  await expect_enabled(send);
  await ta.press("Enter");
}

async function expect_enabled(loc: ReturnType<Page["getByRole"]>): Promise<void> {
  const handle = await loc.elementHandle();
  if (!handle) throw new Error("send button not found");
  const disabled = await handle.evaluate(
    (el) => (el as HTMLButtonElement).disabled,
  );
  if (disabled) throw new Error("send button is disabled — composer busy");
}