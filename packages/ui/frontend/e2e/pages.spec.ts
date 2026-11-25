import { expect, test } from "@playwright/test";

const PAGES: Array<{ path: string; landmark: RegExp }> = [
  { path: "/", landmark: /MONITOR|Play|Architect/i },
  { path: "/play", landmark: /MONITOR Play|session/i },
  { path: "/forge", landmark: /forge|pack|source/i },
  { path: "/gm", landmark: /GM|hook|assistant/i },
  { path: "/forge/worlds", landmark: /world|universe|graph/i },
  { path: "/forge/snapshots", landmark: /snapshot/i },
  { path: "/explorer", landmark: /explorer|graph|filter/i },
  { path: "/search", landmark: /semantic search/i },
  { path: "/settings", landmark: /settings|LLM/i },
  { path: "/forgot-password", landmark: /forgot password/i },
  { path: "/reset-password", landmark: /set a new password/i },
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

/**
 * UX-TENANCY-BO smokes: the backoffice/account surfaces added by the
 * UX-2/UX-3 work. The weekly workflow runs Playwright against a backend
 * started with MONITOR_AUTH_DISABLED=true (local mode), so /admin is open
 * and /settings/account hides the credential cards.
 */
test("/admin renders the operator tabs", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (err) => errors.push(String(err)));

  const response = await page.goto("/admin", { waitUntil: "domcontentloaded" });
  expect(response?.ok(), `HTTP ${response?.status()} for /admin`).toBeTruthy();

  await expect(page.getByRole("heading", { name: "Administration" })).toBeVisible({
    timeout: 15_000,
  });
  for (const label of ["Users", "Invites", "Usage", "Providers"]) {
    await expect(page.getByRole("button", { name: label, exact: true })).toBeVisible();
  }
  // Default tab content mounts alongside the tab strip.
  await expect(page.getByRole("heading", { name: "Users" })).toBeVisible();
  expect(errors, `client errors on /admin: ${errors.join("; ")}`).toEqual([]);
});

test("/settings/account shows local-mode state (no credential cards)", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (err) => errors.push(String(err)));

  const response = await page.goto("/settings/account", { waitUntil: "domcontentloaded" });
  expect(response?.ok(), `HTTP ${response?.status()} for /settings/account`).toBeTruthy();

  await expect(page.getByRole("heading", { name: "Account" })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByRole("heading", { name: "Profile" })).toBeVisible();
  // Local mode (MONITOR_AUTH_DISABLED=true): password change, sessions and
  // API tokens are not offered, so the account page is profile-only.
  await expect(page.getByRole("heading", { name: "Change password" })).toHaveCount(0);
  expect(errors, `client errors on /settings/account: ${errors.join("; ")}`).toEqual([]);
});

test("/gm shows the Prep → Run → Wrap-up stepper", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (err) => errors.push(String(err)));

  const response = await page.goto("/gm", { waitUntil: "domcontentloaded" });
  expect(response?.ok(), `HTTP ${response?.status()} for /gm`).toBeTruthy();

  await expect(page.getByRole("navigation", { name: "Session flow" })).toBeVisible({
    timeout: 15_000,
  });
  await expect(page.getByTestId("gm-step-prep")).toBeVisible();
  await expect(page.getByTestId("gm-step-run")).toBeVisible();
  await expect(page.getByTestId("gm-step-wrap")).toBeVisible();
  expect(errors, `client errors on /gm: ${errors.join("; ")}`).toEqual([]);
});
