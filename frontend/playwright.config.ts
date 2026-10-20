import { defineConfig, devices } from "@playwright/test";

/*
 * End-to-end tests against the real stack: FastAPI backend (port 8100, dev
 * database), the Vite frontend (5180, real API), and the instrumented sample app
 * the test starts itself (9102). Run Postgres first: `docker compose up -d db`.
 */
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = fileURLToPath(new URL(".", import.meta.url));
const win = process.platform === "win32";
const backendPython =
  process.env.BACKEND_PYTHON ?? resolve(here, "../backend/.venv", win ? "Scripts/python.exe" : "bin/python");

export default defineConfig({
  testDir: "./e2e",
  timeout: 120_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: "http://localhost:5180",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: `"${backendPython}" -m uvicorn app.main:app --host 127.0.0.1 --port 8100`,
      cwd: "../backend",
      url: "http://127.0.0.1:8100/api/v1/ready",
      reuseExistingServer: true,
      // Local-development mode, so the sample app on 127.0.0.1 can be a replay target.
      env: { TRACEBACK_REPLAY_ALLOW_PRIVATE_NETWORKS: "true" },
      timeout: 60_000,
    },
    {
      command: "npm run dev",
      url: "http://localhost:5180",
      reuseExistingServer: true,
      env: { VITE_USE_MOCKS: "false" },
      timeout: 60_000,
    },
  ],
});
