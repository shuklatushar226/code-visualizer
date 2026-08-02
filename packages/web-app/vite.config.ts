import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // visualizer-core is a linked workspace and also carries React as a dev
  // dependency for its standalone bundle. Without dedupe, production Rollup
  // can resolve one React copy from web-app and another from visualizer-core,
  // causing an invalid-hook-call crash only after a trace is rendered.
  resolve: {
    dedupe: ["react", "react-dom", "react/jsx-runtime"],
  },
  server: { port: 5173, host: "0.0.0.0" },
});
