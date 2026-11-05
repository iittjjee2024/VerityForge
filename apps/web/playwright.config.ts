import { existsSync } from "node:fs";
import { resolve } from "node:path";
import { defineConfig, devices } from "@playwright/test";

/**
 * E2E against the LIVE backend in mock mode (no API keys, deterministic).
 * Playwright starts both servers; tests exercise the real UI + REST proxy.
 * The API runs with VERITYFORGE_MOCK_MODE=true so every run is reproducible.
 */
// The built next.config.mjs proxies /api/* to VERITYFORGE_API_URL (default http://localhost:8000).
// We bake that env into the web server below AND default the API to 8000 so the proxy resolves either way.
const API_PORT = Number(process.env.VF_E2E_API_PORT ?? 8000);
const WEB_PORT = 3111;

// Resolve the repo venv python to an absolute path (relative exe paths don't resolve via the shell on Windows).
const WIN = resolve(__dirname, "../../.venv/Scripts/python.exe");
const NIX = resolve(__dirname, "../../.venv/bin/python");
const PYTHON = process.env.VF_PYTHON ?? (existsSync(WIN) ? WIN : NIX);

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  expect: { timeout: 10_000 },
  fullyParallel: false, // shared backend state (tasks/audit) — keep specs serial
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: `http://localhost:${WEB_PORT}`,
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      // Mock-mode API: no keys, deterministic. Auth left disabled so write paths are reachable.
      command: `"${PYTHON}" -m uvicorn verityforge.main:app --app-dir ../api --port ${API_PORT}`,
      cwd: ".",
      env: { VERITYFORGE_MOCK_MODE: "true", VERITYFORGE_PERSIST: "false",
             VERITYFORGE_AUTH_SECRET: "", VERITYFORGE_USERS: "", TAVILY_API_KEY: "" },
      port: API_PORT,
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: `npx next start -p ${WEB_PORT}`,
      cwd: ".",
      env: { VERITYFORGE_API_URL: `http://localhost:${API_PORT}` },
      port: WEB_PORT,
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
});
