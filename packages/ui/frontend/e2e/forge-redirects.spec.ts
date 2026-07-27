import { expect, test } from "@playwright/test";

/**
 * F1-1 route consolidation smokes: the pre-Forge routes are redirect shims
 * that land on the new /forge/* section routes, preserving query params.
 */
const REDIRECTS: Array<{ from: string; to: string }> = [
  { from: "/worlds", to: "/forge/worlds" },
  { from: "/worlds?universe=u-smoke", to: "/forge/worlds?universe=u-smoke" },
  { from: "/architect", to: "/forge/architect" },
  { from: "/snapshots", to: "/forge/snapshots" },
  { from: "/snapshots?universe=u-smoke", to: "/forge/snapshots?universe=u-smoke" },
  { from: "/systems", to: "/forge/systems" },
  { from: "/systems?id=sys-smoke", to: "/forge/systems?id=sys-smoke" },
  { from: "/universes", to: "/forge/worlds" },
];

for (const { from, to } of REDIRECTS) {
  test(`redirect ${from} -> ${to}`, async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (err) => errors.push(String(err)));

    await page.goto(from, { waitUntil: "domcontentloaded" });
    await page.waitForURL(`**${to}`, { timeout: 15_000 });

    const landed = new URL(page.url());
    expect(landed.pathname + landed.search).toBe(to);
    expect(errors, `client errors on ${from}: ${errors.join("; ")}`).toEqual([]);
  });
}
