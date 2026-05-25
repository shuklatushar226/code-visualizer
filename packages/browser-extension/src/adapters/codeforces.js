// Codeforces adapter (stub). Codeforces uses a plain <textarea id="sourceCodeTextarea">.

import { mountVisualizer } from "./_common.js";

mountVisualizer({
  match: () => /^\/problemset\/problem\//.test(location.pathname),
  readSource: () => {
    const ta = document.getElementById("sourceCodeTextarea");
    return ta?.value ?? "";
  },
  readStdin: () => {
    const input = document.querySelector(".problem-statement .input pre");
    return input?.innerText ?? "";
  },
  detectLanguage: () => {
    const sel = document.querySelector('select[name="programTypeId"]');
    const label = sel?.options?.[sel.selectedIndex]?.text?.toLowerCase() ?? "";
    if (label.includes("python")) return "python";
    if (label.includes("c++") || label.includes("gcc") || label.includes("g++")) return "cpp";
    return "python";
  },
});
