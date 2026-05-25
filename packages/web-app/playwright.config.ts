import { defineConfig } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(HERE, "..", "..");
const BACKEND_DIR = path.join(REPO_ROOT, "packages", "backend");
const PYTHON = process.env.PYTHON ?? "python3";

export default defineConfig({
  testDir: "./tests",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: "http://localhost:5173",
    headless: true,
    trace: "retain-on-failure",
    video: "retain-on-failure",
  },
  webServer: [
    {
      command: `${PYTHON} -m uvicorn server.main:app --port 8000 --app-dir src`,
      cwd: BACKEND_DIR,
      url: "http://localhost:8000/healthz",
      reuseExistingServer: true,
      timeout: 30_000,
    },
    {
      command: "npm run dev",
      cwd: HERE,
      url: "http://localhost:5173",
      reuseExistingServer: true,
      timeout: 30_000,
    },
  ],
});
