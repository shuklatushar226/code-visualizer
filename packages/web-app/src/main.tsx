import React from "react";
import ReactDOM from "react-dom/client";
import { App } from "./App";
import "@dsa-viz/visualizer-core/src/styles.css";
import "./index.css";

const rootEl = document.getElementById("root");
if (!rootEl) {
  throw new Error("DSA Visualizer: missing #root element");
}

ReactDOM.createRoot(rootEl).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
