# Trace Event Protocol v0.1

A trace is a JSON document with this shape:

```jsonc
{
  "version": "0.1",
  "language": "python" | "cpp",
  "source": "<the original source code as a string>",
  "stdin":  "<the input fed to the program, if any>",
  "stdout": "<everything the program printed>",
  "stderr": "<any error output>",
  "exit":   { "status": "ok" | "error" | "timeout", "message": null },
  "events": [ TraceEvent, ... ]
}
```

A `TraceEvent` is one step of execution (typically one source line):

```jsonc
{
  "t":     0,             // event index, monotonically increasing
  "kind":  "step" | "call" | "return" | "exception" | "stdout",
  "line":  17,            // 1-based line in `source` to highlight
  "file":  "main.py",     // file the line belongs to
  "stack": [Frame, ...],  // bottom-of-stack first
  "heap":  { "<id>": HeapObject, ... },
  "stdout_delta": null,   // string appended this step, or null
  "exception": null       // exception info on the "exception" event
}
```

`Frame`:

```jsonc
{
  "func":    "twoSum",
  "file":    "main.py",
  "line":    17,
  "locals":  { "name": Value, ... },
  "args":    ["nums", "target"]   // parameter names, in order
}
```

`Value` is one of:

```jsonc
// primitives:
{ "kind": "int",    "v": 42 }
{ "kind": "float",  "v": 3.14 }
{ "kind": "bool",   "v": true }
{ "kind": "str",    "v": "hello" }
{ "kind": "none" }

// pointer to a heap object:
{ "kind": "ref", "id": "h_3" }
```

`HeapObject` (kept flat, keyed by id, so the UI can detect sharing/cycles):

```jsonc
// list / vector
{ "kind": "list", "items": [Value, ...] }

// dict / map
{ "kind": "dict", "entries": [[Value, Value], ...] }

// object instance (linked-list node, tree node, custom class)
{
  "kind": "object",
  "type": "ListNode",
  "fields": { "val": Value, "next": Value, "prev": Value }
}

// set
{ "kind": "set", "items": [Value, ...] }

// tuple
{ "kind": "tuple", "items": [Value, ...] }
```

## Why pointer-by-id?

So that the visualizer can:

* Detect when two variables alias the same object (linked-list cycle, shared
  subtree).
* Animate "field changed from X to Y" without re-laying out the whole heap.
* Render arrows between heap nodes cheaply.

## Annotations

The source may contain `# @viz:` comments that the tracer copies into the trace
to override default rendering:

```python
head = ListNode(1)  # @viz: linked-list
graph = defaultdict(list)  # @viz: graph
heap = []  # @viz: heap
```

Annotations are advisory — the structure detector wins ties when conflicting.

## Size limits

* `events` is capped at `MAX_TRACE_EVENTS` (default 5000). Programs exceeding
  this produce a `truncated` exit status with a partial trace.
* Each `Value.v` string is capped at 1 KiB; longer strings are stored once in
  the heap and referenced.
* The heap is **incremental**: each event includes only objects that changed
  since the previous event. The UI maintains a running snapshot. (Wire format
  may compress this further with JSON-patch later; v0.1 keeps it simple by
  sending the whole heap each step.)

## Schema validation

The canonical JSON Schema lives at `packages/trace-schema/schema/trace.schema.json`.
TypeScript types live at `packages/trace-schema/src/index.ts`. Both are
generated from the same source; do not edit them independently.
