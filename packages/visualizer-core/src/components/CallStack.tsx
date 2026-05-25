import React from "react";
import type { Frame, Value } from "@dsa-viz/trace-schema";

export interface CallStackProps {
  frames: Frame[];
}

export const CallStack: React.FC<CallStackProps> = ({ frames }) => {
  return (
    <div className="dsa-viz-callstack">
      <h3 className="dsa-viz-section-title">Call stack</h3>
      {frames.length === 0 && <div className="dsa-viz-empty">(no frames)</div>}
      <ol className="dsa-viz-frames">
        {frames.map((f, idx) => {
          const top = idx === frames.length - 1;
          return (
            <li
              key={idx}
              className={["dsa-viz-frame", top ? "is-top" : ""].join(" ")}
            >
              <div className="dsa-viz-frame-head">
                <span className="dsa-viz-frame-func">{f.func}</span>
                <span className="dsa-viz-frame-line">:{f.line}</span>
              </div>
              <table className="dsa-viz-locals">
                <tbody>
                  {Object.entries(f.locals).map(([name, value]) => (
                    <tr key={name}>
                      <td className="dsa-viz-local-name">{name}</td>
                      <td className="dsa-viz-local-value">
                        <ValueChip value={value} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </li>
          );
        })}
      </ol>
    </div>
  );
};

/**
 * Renders one Value as an inline chip. Refs render as `→h_3` so the user can
 * trace where it points; primitive values render literally.
 */
const ValueChip: React.FC<{ value: Value }> = ({ value }) => {
  switch (value.kind) {
    case "int":
    case "float":
      return <span className="dsa-viz-chip is-num">{String(value.v)}</span>;
    case "bool":
      return <span className="dsa-viz-chip is-bool">{value.v ? "true" : "false"}</span>;
    case "str":
      return <span className="dsa-viz-chip is-str">"{value.v}"</span>;
    case "none":
      return <span className="dsa-viz-chip is-none">None</span>;
    case "ref":
      return <span className="dsa-viz-chip is-ref">→{value.id}</span>;
  }
};
