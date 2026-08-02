import React from "react";
import type { Frame, HeapObject, Value } from "@dsa-viz/trace-schema";
import { formatScalar } from "../lib/formatScalar";

export interface CallStackProps {
  frames: Frame[];
  heap?: Record<string, HeapObject>;
}

export const CallStack: React.FC<CallStackProps> = ({ frames, heap = {} }) => {
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
                        <ValueChip value={value} heap={heap} />
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
 * Renders one Value as an inline chip. References use the pointed-to object's
 * type and value rather than exposing Python's process-specific memory id.
 */
const ValueChip: React.FC<{ value: Value; heap: Record<string, HeapObject> }> = ({
  value,
  heap,
}) => {
  switch (value.kind) {
    case "int":
    case "float":
      // Big ints arrive as exact decimal strings; non-finite floats carry an
      // inf/-inf/nan sentinel — formatScalar renders both correctly.
      return <span className="dsa-viz-chip is-num">{formatScalar(value)}</span>;
    case "bool":
      return <span className="dsa-viz-chip is-bool">{value.v ? "true" : "false"}</span>;
    case "str":
      return <span className="dsa-viz-chip is-str">"{value.v}"</span>;
    case "none":
      return <span className="dsa-viz-chip is-none">None</span>;
    case "ref":
      return (
        <span className="dsa-viz-chip is-ref" title={`heap reference ${value.id}`}>
          → {describeReference(value, heap)}
        </span>
      );
  }
};

/** Turn an opaque heap reference into a stable, human-readable description. */
export function describeReference(
  value: Extract<Value, { kind: "ref" }>,
  heap: Record<string, HeapObject>,
): string {
  const target = heap[value.id];
  if (!target) return "reference";

  switch (target.kind) {
    case "list":
      return `list[${target.items.length}]`;
    case "tuple":
      return `tuple[${target.items.length}]`;
    case "set":
      return `set[${target.items.length}]`;
    case "dict":
      return `dict[${target.entries.length}]`;
    case "object": {
      const displayValue = target.fields.val ?? target.fields.data ?? target.fields.value;
      return displayValue
        ? `${target.type}(${describeInlineValue(displayValue)})`
        : target.type;
    }
  }
}

function describeInlineValue(value: Value): string {
  switch (value.kind) {
    case "int":
    case "float":
    case "str":
    case "bool":
      return formatScalar(value);
    case "none":
      return "None";
    case "ref":
      return "object";
  }
}
