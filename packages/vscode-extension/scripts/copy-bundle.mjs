#!/usr/bin/env node
/**
 * Copy the visualizer-core standalone bundle into media/ so the webview
 * can load it via vscode-webview-resource URIs.
 */
import { execSync } from "node:child_process";
import { cpSync, existsSync, mkdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const EXT_ROOT = path.resolve(HERE, "..");
const CORE = path.resolve(EXT_ROOT, "..", "visualizer-core");
const MEDIA = path.join(EXT_ROOT, "media");

const bundle = path.join(CORE, "dist", "standalone.mjs");
const css = path.join(CORE, "dist", "standalone.css");
if (!existsSync(bundle)) {
  console.log("[vscode-ext] Building visualizer-core standalone bundle...");
  execSync("npx vite build -c vite.lib.config.ts", { cwd: CORE, stdio: "inherit" });
}

if (!existsSync(MEDIA)) mkdirSync(MEDIA, { recursive: true });
cpSync(bundle, path.join(MEDIA, "standalone.mjs"));
cpSync(css, path.join(MEDIA, "standalone.css"));
console.log(`[vscode-ext] bundle copied into ${MEDIA}`);
