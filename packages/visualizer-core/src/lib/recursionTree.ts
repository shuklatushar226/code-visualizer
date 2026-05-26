import type { Frame, TraceEvent, Value } from "@dsa-viz/trace-schema";

export interface CallNode {
  id: string;
  func: string;
  args: Record<string, Value>;
  startEvent: number;
  endEvent?: number;
  children: CallNode[];
  /** True for synthetic "+N more" nodes inserted when maxNodes is hit. */
  truncated?: boolean;
}

export interface BuildOptions {
  /** Stop pushing new call nodes once this many real nodes exist. */
  maxNodes?: number;
}

/**
 * Build a recursion tree from the event sequence. Drives off the `call` and
 * `return` event kinds (the trace contract guarantees one per function
 * boundary). Stack-depth diffing alone is insufficient because a return-and-
 * recurse pair like `fib(n-1) + fib(n-2)` leaves total stack depth unchanged
 * across the two recursive calls.
 *
 * The synthetic root represents "before any code ran" and is filtered out
 * by the view; tests use it to make the API total over empty traces.
 */
export function buildRecursionTree(events: TraceEvent[], opts: BuildOptions = {}): CallNode {
  const maxNodes = opts.maxNodes ?? Infinity;
  const root: CallNode = {
    id: "root",
    func: "<root>",
    args: {},
    startEvent: 0,
    children: [],
  };
  const open: CallNode[] = [root];
  let counter = 0;
  let realNodes = 0;
  // Once we've hit the cap we still drain the call/return tape so endEvents
  // for already-open nodes resolve correctly, but new pushes become a single
  // synthetic "+N more" sibling on the current parent.
  const truncated: Set<CallNode> = new Set();

  events.forEach((ev, i) => {
    if (ev.kind === "call") {
      const top = ev.stack[ev.stack.length - 1];
      if (!top) return;
      const parent = open[open.length - 1];
      if (realNodes >= maxNodes) {
        // Mark the parent so the view can render a single ellipsis child.
        if (!truncated.has(parent)) {
          parent.children.push({
            id: `n_truncated_${counter++}`,
            func: "+more",
            args: {},
            startEvent: i,
            endEvent: i,
            children: [],
            truncated: true,
          });
          truncated.add(parent);
        }
        // Push a placeholder so depth tracking continues to work for matching returns.
        open.push({ id: "placeholder", func: "", args: {}, startEvent: i, children: [], truncated: true });
        return;
      }
      const node: CallNode = {
        id: `n_${counter++}`,
        func: top.func,
        args: pickArgs(top),
        startEvent: i,
        children: [],
      };
      parent.children.push(node);
      open.push(node);
      realNodes += 1;
    } else if (ev.kind === "return") {
      if (open.length > 1) {
        const popped = open.pop()!;
        if (!popped.truncated) popped.endEvent = i;
      }
    }
  });

  // Close any frames still open at the end.
  const lastIdx = Math.max(0, events.length - 1);
  for (let i = open.length - 1; i > 0; i--) {
    if (!open[i].truncated) open[i].endEvent = lastIdx;
  }
  return root;
}

function pickArgs(frame: Frame): Record<string, Value> {
  const out: Record<string, Value> = {};
  for (const name of frame.args) {
    if (name in frame.locals) out[name] = frame.locals[name];
  }
  return out;
}

/**
 * Find the deepest call node whose [startEvent, endEvent] contains t. Returns
 * null if t falls outside every non-root node (e.g., before any call).
 */
export function findActiveCall(
  root: CallNode,
  t: number,
  fallbackEnd: number,
): CallNode | null {
  function descend(node: CallNode): CallNode | null {
    const end = node.endEvent ?? fallbackEnd;
    if (t < node.startEvent || t > end) return null;
    for (const child of node.children) {
      const hit = descend(child);
      if (hit) return hit;
    }
    return node.id === "root" ? null : node;
  }
  return descend(root);
}

/**
 * Render one Value for display on a recursion-tree node label.
 *
 * - Heap refs collapse to `→<last-4-digits>` so the args line stays scannable
 *   without burning 12+ chars per pointer. The reader can cross-reference the
 *   last-4 tag with the Heap view when they care about identity.
 * - Strings are JSON-escaped and capped at 14 visible chars.
 * - All other primitives render as their Python-style literal.
 */
export function formatArgValue(v: Value): string {
  switch (v.kind) {
    case "int":
    case "float":
      return String(v.v);
    case "bool":
      return v.v ? "True" : "False";
    case "str": {
      const s = JSON.stringify(v.v);
      return s.length > 14 ? s.slice(0, 13) + "…" : s;
    }
    case "none":
      return "None";
    case "ref": {
      const tail = v.id.replace(/^h_/, "").slice(-4);
      return `→${tail}`;
    }
  }
}

/**
 * Build the args label that hangs under each recursion-tree node.
 *
 * - Drops Python's implicit `self`: it's always there for instance methods,
 *   always a heap-ref, and never carries info. Including it ate so much of
 *   the budget that the actually-distinguishing arg (`val=1` vs `val=2` etc.)
 *   got chopped by truncation.
 * - Caps the joined label at 32 chars with a trailing ellipsis. The component
 *   pairs this with a `<title>` tooltip that always shows the full args.
 */
export function formatArgs(args: Record<string, Value>): string {
  const parts: string[] = [];
  for (const [k, v] of Object.entries(args)) {
    if (k === "self") continue;
    parts.push(`${k}=${formatArgValue(v)}`);
  }
  const joined = parts.join(", ");
  const CAP = 32;
  return joined.length > CAP ? joined.slice(0, CAP - 1) + "…" : joined;
}

/** Verbose args label used by the SVG `<title>` tooltip — no truncation,
 *  includes `self` so power users can correlate the full picture. */
export function formatArgsVerbose(args: Record<string, Value>): string {
  const parts: string[] = [];
  for (const [k, v] of Object.entries(args)) {
    parts.push(`${k}=${formatArgValue(v)}`);
  }
  return parts.join(", ");
}

export function countCalls(root: CallNode): number {
  let n = 0;
  function walk(node: CallNode): void {
    if (node.id !== "root" && !node.truncated) n += 1;
    node.children.forEach(walk);
  }
  walk(root);
  return n;
}
