import { expect, test } from "@playwright/test";

const PAGES: Array<{ path: string; landmark: RegExp }> = [
  { path: "/", landmark: /MONITOR|Play|Architect/i },
  { path: "/play", landmark: /MONITOR Play|session/i },
  { path: "/forge", landmark: /forge|pack|source/i },
  { path: "/gm", landmark: /GM|hook|assistant/i },
  { path: "/worlds", landmark: /world|universe|graph/i },
  { path: "/snapshots", landmark: /snapshot/i },
  { path: "/explorer", landmark: /explorer|graph|filter/i },
  { path: "/search", landmark: /semantic search/i },
  { path: "/settings", landmark: /settings|LLM/i },
];

for (const { path, landmark } of PAGES) {
  test(`page ${path} renders without crashing`, async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (err) => errors.push(String(err)));

    const response = await page.goto(path, { waitUntil: "domcontentloaded" });
    expect(response?.ok(), `HTTP ${response?.status()} for ${path}`).toBeTruthy();

    await expect(page.locator("body")).toContainText(landmark, { timeout: 15_000 });
    expect(errors, `client errors on ${path}: ${errors.join("; ")}`).toEqual([]);
  });
}
