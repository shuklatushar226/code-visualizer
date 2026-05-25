/**
 * Standalone entry point: bundles React + visualizer-core into a single
 * ES module so the browser extension's iframe and the VS Code webview
 * can mount the panel without their own bundler.
 *
 * Both surfaces:
 *   import { mountVisualizer } from "./standalone.mjs";
 *   const handle = mountVisualizer(document.getElementById("root"), trace);
 *   // later: handle.unmount();
 */
import React from "react";
import { createRoot, type Root } from "react-dom/client";
import type { Trace } from "@dsa-viz/trace-schema";
import { VisualizerPanel } from "./components/VisualizerPanel";
import "./styles.css";

export interface MountHandle {
  unmount(): void;
  update(trace: Trace): void;
}

export function mountVisualizer(container: HTMLElement, trace: Trace): MountHandle {
  const root: Root = createRoot(container);
  let current = trace;
  root.render(React.createElement(VisualizerPanel, { trace: current }));
  return {
    unmount() {
      root.unmount();
    },
    update(next: Trace) {
      current = next;
      root.render(React.createElement(VisualizerPanel, { trace: current }));
    },
  };
}
