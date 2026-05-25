// LeetCode adapter. Reads the Monaco editor and the testcase pane.
//
// Why grabbing from Monaco directly?  LeetCode's React tree changes a lot
// across redesigns, but the actual editor instance is always exposed at
// `window.monaco.editor.getModels()[0]`. This stays stable across UI
// revamps.

// Loaded after _common.js (manifest js[] order), which sets
// window.__dsaMountVisualizer.

const LANGUAGE_BY_LABEL = {
  python: "python",
  python3: "python",
  cpp: "cpp",
  "c++": "cpp",
};

window.__dsaMountVisualizer({
  match: () => /^\/problems\//.test(location.pathname),
  readSource: () => {
    try {
      const models = window.monaco?.editor?.getModels?.() ?? [];
      const editorModel = models.find((m) => m.uri?.path?.endsWith(".py")) ?? models[0];
      return editorModel?.getValue?.() ?? "";
    } catch {
      return "";
    }
  },
  readStdin: () => {
    // LeetCode renders the testcase in a textarea once expanded.
    const ta = document.querySelector('[data-cy="testcase-input"] textarea')
            ?? document.querySelector('textarea[placeholder*="case"]');
    return ta?.value ?? "";
  },
  detectLanguage: () => {
    const labelEl = document.querySelector('[data-cy="lang-select"] button')
                 ?? document.querySelector('[class*="lang-select"]');
    const label = (labelEl?.textContent || "").trim().toLowerCase();
    return LANGUAGE_BY_LABEL[label] ?? "python";
  },
});
