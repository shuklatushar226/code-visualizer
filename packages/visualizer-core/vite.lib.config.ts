import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  plugins: [react()],
  define: {
    // React's UMD/CJS dev branch references process.env.NODE_ENV; statically
    // replace it so the bundle works in a plain browser context.
    "process.env.NODE_ENV": JSON.stringify("production"),
  },
  build: {
    lib: {
      entry: path.resolve(HERE, "src/standalone.tsx"),
      formats: ["es"],
      fileName: () => "standalone.mjs",
    },
    outDir: "dist",
    emptyOutDir: false,
    cssCodeSplit: false,
    rollupOptions: {
      // React/ReactDOM inlined so the bundle is self-contained for an
      // extension iframe / VS Code webview that doesn't run npm install.
      external: [],
      output: {
        assetFileNames: (info) => (info.name?.endsWith(".css") ? "standalone.css" : "[name][extname]"),
      },
    },
    sourcemap: false,
    minify: true,
  },
});
