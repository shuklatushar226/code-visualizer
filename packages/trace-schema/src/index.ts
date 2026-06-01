/**
 * Trace Event Protocol — TypeScript types.
 *
 * Mirrors docs/TRACE_FORMAT.md. Keep this file in sync with the JSON schema
 * at ../schema/trace.schema.json. (A future build step will generate one
 * from the other.)
 */

export type Language = "python" | "cpp" | "javascript" | "java";

export interface Trace {
  version: "0.1";
  language: Language;
  source: string;
  stdin: string;
  stdout: string;
  stderr: string;
  exit: ExitInfo;
  events: TraceEvent[];
  /** Optional per-local rendering hints parsed from `# @viz:` comments. */
  annotations?: Record<string, string>;
}

export interface ExitInfo {
  status: "ok" | "error" | "timeout";
  message: string | null;
  truncated?: boolean;
}

export type EventKind =
  | "step"
  | "call"
  | "return"
  | "exception"
  | "stdout";

export interface TraceEvent {
  t: number;
  kind: EventKind;
  line: number;
  file: string;
  stack: Frame[];
  heap: Heap;
  stdout_delta: string | null;
  exception: ExceptionInfo | null;
}

export interface ExceptionInfo {
  type: string;
  message: string;
}

export interface Frame {
  func: string;
  file: string;
  line: number;
  locals: Record<string, Value>;
  args: string[];
}

// ---------------- Values & heap ---------------- //

export type Value =
  // `v` is a string (with `big: true`) when the integer exceeds JS's safe
  // range (2**53), so the exact value survives JSON round-tripping.
  | { kind: "int"; v: number | string; big?: boolean }
  // Non-finite floats can't be expressed in strict JSON, so `v` is null and
  // `special` carries the sentinel.
  | { kind: "float"; v: number | null; special?: "inf" | "-inf" | "nan" }
  | { kind: "bool"; v: boolean }
  | { kind: "str"; v: string }
  | { kind: "none" }
  | { kind: "ref"; id: string };

export type Heap = Record<string, HeapObject>;

export type HeapObject =
  | { kind: "list"; items: Value[]; subkind?: string }
  | { kind: "tuple"; items: Value[] }
  | { kind: "set"; items: Value[] }
  | { kind: "dict"; entries: Array<[Value, Value]> }
  | { kind: "object"; type: string; fields: Record<string, Value> };

// ---------------- Helpers ---------------- //

export function isRef(v: Value): v is { kind: "ref"; id: string } {
  return v.kind === "ref";
}

export function deref(heap: Heap, v: Value): HeapObject | null {
  return isRef(v) ? heap[v.id] ?? null : null;
}
