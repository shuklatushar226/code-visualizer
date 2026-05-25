import { defineConfig } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  testDir: "./tests",
  timeout: 30_000,
  fullyParallel: false,
  workers: 1,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: "http://localhost:8765",
    headless: true,
  },
  webServer: [
    {
      // Serve the built dist on :8765. The extension must already be built;
      // CI does this in the previous step. Locally, run `npm run build` first.
      command: "python3 -m http.server 8765",
      cwd: path.join(HERE, "dist"),
      url: "http://localhost:8765/smoke.html",
      reuseExistingServer: true,
      timeout: 10_000,
    },
  ],
});
