#!/usr/bin/env node
/**
 * Build the unpacked browser-extension into `dist/`.
 *
 * Steps:
 *   1. Build the visualizer-core standalone bundle.
 *   2. Copy the bundle (standalone.mjs + standalone.css) alongside the panel.
 *   3. Copy the rest of the extension source into `dist/` so Chrome can load
 *      it as an unpacked extension from a single directory.
 */
import { execSync } from "node:child_process";
import { cpSync, existsSync, mkdirSync, rmSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const EXT_ROOT = path.resolve(HERE, "..");
const REPO_ROOT = path.resolve(EXT_ROOT, "..", "..");
const CORE = path.join(REPO_ROOT, "packages", "visualizer-core");
const DIST = path.join(EXT_ROOT, "dist");

console.log("[ext-build] Building visualizer-core standalone bundle...");
// Invoke vite directly so we don't depend on the parent's npm version.
execSync("npx vite build -c vite.lib.config.ts", {
  cwd: CORE,
  stdio: "inherit",
});

if (existsSync(DIST)) rmSync(DIST, { recursive: true });
mkdirSync(DIST, { recursive: true });

// Copy the entire extension source tree.
cpSync(path.join(EXT_ROOT, "manifest.json"), path.join(DIST, "manifest.json"));
cpSync(path.join(EXT_ROOT, "src"), path.join(DIST, "src"), { recursive: true });

// Drop the standalone bundle next to panel/index.html so relative imports work.
const panelDir = path.join(DIST, "src", "panel");
cpSync(path.join(CORE, "dist", "standalone.mjs"), path.join(panelDir, "standalone.mjs"));
cpSync(path.join(CORE, "dist", "standalone.css"), path.join(panelDir, "standalone.css"));

// Copy any test fixtures (e.g. smoke.html) into dist for local serving.
const fixtures = path.join(EXT_ROOT, "fixtures");
if (existsSync(fixtures)) {
  cpSync(fixtures, DIST, { recursive: true });
}

console.log(`[ext-build] dist ready at ${DIST}`);
