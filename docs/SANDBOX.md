# Sandbox model

Student code is **untrusted**. The backend never runs it in-process; it
hands the source to a sandboxed subprocess that produces a Trace Event
Protocol JSON document on stdout. Three layers of defence stack:

1. **Process boundary**: subprocess with a wall-clock timeout in the
   parent. The tracer-python and tracer-cpp packages know nothing about
   the server's HTTP layer, so a tracer crash can't escape the worker.

2. **POSIX rlimits**: `setrlimit(RLIMIT_CPU, ...)`, `RLIMIT_AS`,
   `RLIMIT_FSIZE`, `RLIMIT_NPROC`, `RLIMIT_CORE`. Applied via
   `preexec_fn` in `packages/backend/src/server/sandbox.py`. Each one is
   best-effort and wrapped in try/except so the child still starts when
   a particular limit isn't honoured on the current OS (notably
   `RLIMIT_AS` on macOS Apple Silicon).

3. **Container (recommended for any hosted deployment)**:
   `packages/backend/Dockerfile.sandbox` builds a minimal image with
   Python 3.13 + g++ + gdb pre-installed. Invoke per request:

   ```bash
   docker run --rm -i \
     --network=none \
     --read-only --tmpfs /tmp:size=64m,exec --tmpfs /tmp/work:size=64m,exec \
     --memory=256m --cpus=1 \
     --security-opt seccomp=$(pwd)/packages/backend/sandbox.seccomp.json \
     dsa-viz-sandbox -c "$LAUNCHER" <<< "$SOURCE"
   ```

   The flags collectively give: no network, read-only root filesystem,
   bounded tmpfs for compilation artifacts, hard CPU + memory caps, and
   a deny-by-default seccomp profile that only allows the syscalls
   Python + g++ + gdb actually need.

   The image and seccomp profile are starting points — tighten the
   syscall allowlist further if you have a narrower workload.

   The seccomp profile (`packages/backend/sandbox.seccomp.json`) starts
   from Docker's default-deny and allows only the syscalls Python +
   g++ + gdb need. Keep it strict JSON — Docker's libseccomp rejects
   unknown top-level keys, so don't add `_comment` fields or similar.

## gVisor (defence in depth)

For untrusted multi-tenant hosting, replace `--runtime=runc` with
`--runtime=runsc` (gVisor). gVisor runs the container's syscalls
through a user-space kernel implementation, so an exploit that escapes
the sandbox process still hits a fake kernel before touching the host.

```bash
docker run --runtime=runsc <other flags> dsa-viz-sandbox ...
```

## What this does **not** protect against

- **Side-channels** (timing, cache). Don't run latency-sensitive
  workloads on the same host.
- **Resource exhaustion via many tiny requests**. Apply rate limiting
  at the HTTP layer.
- **Container-escape 0-days**. gVisor is the answer; alternatively
  Firecracker microVMs.

## Verifying the boundary

`packages/backend/tests/test_sandbox.py` covers the in-process layer:
timeouts, runtime errors, compile errors, source-size guards. Add new
adversarial sources to that file when you discover an escape (and fix
the escape first).

For Docker-based testing, the smoke script you can run locally:

```bash
echo "import os; os.system('curl example.com')" | \
  docker run --rm -i --network=none dsa-viz-sandbox -c "$(cat <<'PY'
import sys; exec(sys.stdin.read())
PY
)"
```

Should fail to reach the network. If it doesn't, the sandbox is broken.
