import type { HeapObject, Value } from "@dsa-viz/trace-schema";
import { formatScalar } from "./formatScalar";

/** Turn an opaque runtime heap reference into a stable learner-facing label. */
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
