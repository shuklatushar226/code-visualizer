import type { Value } from "@dsa-viz/trace-schema";

/**
 * Render an int / float / str / bool Value to a display string.
 *
 * Handles two encodings that a naive `String(v.v)` gets wrong:
 *   - big integers arrive as exact decimal strings (v is already a string);
 *   - non-finite floats carry a `special` sentinel with v === null, because
 *     strict JSON cannot represent inf / -inf / nan.
 */
export function formatScalar(v: Value): string {
  if (v.kind === "float") {
    if (v.special === "inf") return "∞";
    if (v.special === "-inf") return "−∞";
    if (v.special === "nan") return "NaN";
    return String(v.v);
  }
  return String((v as { v: unknown }).v);
}
