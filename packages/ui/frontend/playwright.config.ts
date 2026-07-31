import { defineConfig, devices } from "@playwright/test";

/**
 * Page smokes (FINAL_FABLE T-041): every major route mounts and renders its
 * landmark UI without client-side crashes. Data calls hit the backend when
 * it's up (rewrites proxy /api to NEXT_PUBLIC_API_URL, default :8000 via env
 * at `npm run build`); pages must still render their shells when it's not.
 *
 * Run: npm run build && npx playwright test
 * (serves the production standalone build on :3100 — dev-mode per-page
 * compiles are too slow for smoke budgets)
 *
 * L3 roleplay project (see docs/testing/PLAYWRIGHT_LLM_ROLEPLAY.md): opt-in
 * via E2E_ROLEPLAY=1. Requires the full backend stack with Ollama so it
 * is excluded from PR CI by default; the nightly pipeline flips the env.
 */
const ROLEPLAY = process.env.E2E_ROLEPLAY === "1";

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  retries: 0,
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
    ...(ROLEPLAY
      ? [
          {
            name: "roleplay",
            testMatch: /roleplay\.spec\.ts$/,
            use: {
              ...devices["Desktop Chrome"],
              baseURL:
                process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3100",
              trace: "on" as const,
              video: "retain-on-failure" as const,
              screenshot: "only-on-failure" as const,
              launchOptions: process.env.PW_SLOWMO
                ? { slowMo: Number(process.env.PW_SLOWMO) }
                : undefined,
            },
            timeout: 900_000,
            expect: { timeout: 15_000 },
          },
        ]
      : []),
  ],
  use: {
    baseURL: "http://localhost:3100",
  },
  webServer: {
    command: "./e2e-server.sh",
    url: "http://localhost:3100",
    reuseExistingServer: true,
    timeout: 90_000,
    env: {
      NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
    },
  },
});