# Reliability and 1,000-case soak test

The repository includes a deterministic HTTP soak suite that drives the same
combined FastAPI/Vite Docker image deployed to Render. It sends source code
through the public `/trace` contract and validates both program behavior and
the returned Trace Event Protocol.

## Coverage

The suite contains exactly 1,000 independent requests:

| Runtime or boundary | Cases | What is exercised |
| --- | ---: | --- |
| Python | 870 | arithmetic, loops, collections, stdin, recursion, linked lists, graphs, sorting, runtime errors, syntax errors |
| JavaScript | 90 | arrays, recursion, objects, maps, loops, runtime errors |
| C++ | 30 | arithmetic, vectors, loops, recursion, compiler errors |
| API validation | 10 | unsupported languages, missing fields, invalid field types |

For every successful trace, the harness checks protocol version, language and
source identity, exit state, expected Python stdout, sequential event indexes,
event kinds, source positions, stack-frame shape, encoded local values, heap
object kinds, and the 5,000-event ceiling. Expected user-code failures pass
only when they return the correct structured error response.

## Reproduce locally

```bash
docker build -t code-visualizer:soak .
docker run --rm --name code-visualizer-soak \
  -p 18080:8000 \
  -e TRACE_RATE_PER_MINUTE=10000 \
  -e MAX_CONCURRENT_TRACES=6 \
  code-visualizer:soak

# In another terminal
npm run test:soak
```

The rate-limit override is for the isolated local test container only. Do not
run the full suite against the public demo, whose admission controls are part
of its production safety boundary.

## Verified run

On 2026-08-03, the production Docker image completed **1,000/1,000 cases** in
50.390 seconds with **24,661 trace events** validated and no failed cases.
Observed request latency was 25.440 ms at p50 and 882.439 ms at p95. The run
also exposed and led to a fix for JavaScript traces stepping through Node.js
internals after user code had completed; a representative trace improved from
21.669 seconds and 445 noisy events to 0.910 seconds and 13 meaningful events.

This is strong regression evidence for the tested runtime and protocol paths,
not a claim that arbitrary untrusted programs or every possible algorithm are
bug-free. See [SANDBOX.md](SANDBOX.md) for the deployment security boundary.
