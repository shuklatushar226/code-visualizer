// HackerRank adapter (stub). HackerRank uses a CodeMirror 5 instance whose
// model lives at `document.querySelector(".CodeMirror").CodeMirror`.

window.__dsaMountVisualizer({
  match: () => /\/challenges\//.test(location.pathname),
  readSource: () => {
    const cm = document.querySelector(".CodeMirror")?.CodeMirror;
    return cm?.getValue?.() ?? "";
  },
  readStdin: () => {
    const ta = document.querySelector('textarea[data-attr="custom-input"]');
    return ta?.value ?? "";
  },
  detectLanguage: () => "python",
});
