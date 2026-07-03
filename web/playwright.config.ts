import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright config — happy-path E2E from signup to saved listing.
 *
 * Expectations:
 *   1. Backend (uvicorn) is running on http://127.0.0.1:8000 (or set BASE_URL)
 *   2. Frontend is running on http://localhost:3000 (or set FRONTEND_URL)
 *
 * In CI:
 *   - The `webServer` block starts the backend on port 8765.
 *   - The frontend (next dev or next start) is started in a sibling step.
 *
 * Run locally:
 *   cd web && npm install
 *   npx playwright install chromium
 *   npm run test:e2e
 */

const FRONTEND_URL = process.env.FRONTEND_URL || "http://localhost:3000";
const BACKEND_URL = process.env.BACKEND_URL || "http://127.0.0.1:8000";

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: [["list"]],
  use: {
    baseURL: FRONTEND_URL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    extraHTTPHeaders: {},
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        // Use the configured backend for direct API requests in setup.
        extraHTTPHeaders: {
          "X-Test-Backend": BACKEND_URL,
        },
      },
    },
  ],
  // Spin up the backend alongside the test if CI is set.
  webServer: process.env.CI
    ? {
        command: "cd ../backend && . .venv/bin/activate && uvicorn app.main:app --host 127.0.0.1 --port 8765",
        url: "http://127.0.0.1:8765/health",
        reuseExistingServer: false,
        timeout: 60_000,
      }
    : undefined,
});
