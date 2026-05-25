import React, { useMemo } from "react";

export interface CodePaneProps {
  source: string;
  language: "python" | "cpp";
  currentLine?: number;
}

/**
 * Renders the source code with the active line highlighted. Kept dependency-
 * free on purpose so the same component works inside the browser extension's
 * lightweight bundle. Drop in `react-syntax-highlighter` or `monaco` from the
 * host app if you want richer highlighting.
 */
export const CodePane: React.FC<CodePaneProps> = ({ source, language, currentLine }) => {
  const lines = useMemo(() => source.split(/\r?\n/), [source]);

  return (
    <pre className="dsa-viz-codepane" data-language={language}>
      {lines.map((line, i) => {
        const lineNo = i + 1;
        const active = lineNo === currentLine;
        return (
          <div
            key={lineNo}
            className={["dsa-viz-codeline", active ? "is-active" : ""].join(" ")}
            data-line={lineNo}
          >
            <span className="dsa-viz-gutter">{lineNo}</span>
            <span className="dsa-viz-linebody">{line || " "}</span>
          </div>
        );
      })}
    </pre>
  );
};
