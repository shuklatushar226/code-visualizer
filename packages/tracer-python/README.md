# dsa-tracer (Python)

A tiny tracer that runs a Python program with `sys.settrace` and emits a JSON
document conforming to the Trace Event Protocol (see `docs/TRACE_FORMAT.md`).

## Install

```bash
pip install -e .
```

## Usage

```bash
# Write trace to a file:
dsa-trace path/to/solution.py --output trace.json

# Or pipe to stdout:
dsa-trace path/to/solution.py

# With stdin:
echo "3 1 4 1 5" | dsa-trace path/to/sum.py --stdin -
```

## Library use

```python
from dsa_tracer import trace_source

src = open("solution.py").read()
result = trace_source(src, stdin="", max_events=5000)
print(result["events"][0])
```

## What it captures

For each executed line of the user's source file:

* The line number to highlight
* The full call stack with each frame's locals
* A heap snapshot of every reachable object, keyed by `id()`
* Anything written to `stdout` since the previous step

Library and standard-library frames are skipped — only frames whose file
matches the user's source are recorded.

## Limits

* Hard cap on number of events (`--max-events`, default 5000)
* Hard cap on string length per value (1024 bytes)
* No interactive `input()` — feed stdin upfront
