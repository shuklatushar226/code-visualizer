import { defineConfig } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(HERE, "..", "..");
const BACKEND_DIR = path.join(REPO_ROOT, "packages", "backend");
const PYTHON = process.env.PYTHON ?? "python3";
const BACKEND_PORT = process.env.E2E_BACKEND_PORT ?? "8000";
const WEB_PORT = process.env.E2E_WEB_PORT ?? "5173";
const BACKEND_URL = `http://localhost:${BACKEND_PORT}`;
const WEB_URL = `http://localhost:${WEB_PORT}`;

export default defineConfig({
  testDir: "./tests",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: WEB_URL,
    headless: true,
    trace: "retain-on-failure",
    video: "retain-on-failure",
  },
  webServer: [
    {
      command: `${PYTHON} -m uvicorn server.main:app --port ${BACKEND_PORT} --app-dir src`,
      cwd: BACKEND_DIR,
      env: { ALLOWED_ORIGINS: WEB_URL },
      url: `${BACKEND_URL}/healthz`,
      reuseExistingServer: true,
      timeout: 30_000,
    },
    {
      command: `npm run dev -- --port ${WEB_PORT}`,
      cwd: HERE,
      env: { VITE_API_URL: BACKEND_URL },
      url: WEB_URL,
      reuseExistingServer: true,
      timeout: 30_000,
    },
  ],
});
