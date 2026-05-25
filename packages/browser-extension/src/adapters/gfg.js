// GeeksforGeeks Practice adapter (stub). GfG uses an Ace editor; the
// instance is accessible via `window.ace.edit(<node>)`.

import { mountVisualizer } from "./_common.js";

mountVisualizer({
  match: () => /^\/problems\//.test(location.pathname),
  readSource: () => {
    const node = document.querySelector("#editor, .ace_editor");
    if (!node) return "";
    try {
      const editor = window.ace?.edit?.(node);
      return editor?.getValue?.() ?? "";
    } catch {
      return "";
    }
  },
  readStdin: () => "",
  detectLanguage: () => "python",
});
