import { defineConfig } from "@playwright/test";

/**
 * Page smokes (FINAL_FABLE T-041): every major route mounts and renders its
 * landmark UI without client-side crashes. Data calls hit the backend when
 * it's up (rewrites proxy /api to NEXT_PUBLIC_API_URL, default :8000 via env
 * at `npm run build`); pages must still render their shells when it's not.
 *
 * Run: npm run build && npx playwright test
 * (serves the production standalone build on :3100 — dev-mode per-page
 * compiles are too slow for smoke budgets)
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  retries: 0,
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
