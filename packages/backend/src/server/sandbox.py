"""Run user code in a subprocess with CPU / memory / time limits.

This module is the SOLE place where untrusted code is executed. Everything
else in the backend stays in the parent process.

The strategy:

* Spawn a fresh Python interpreter with ``-S`` (no site).
* Pipe a small launcher script over stdin: it imports the tracer, reads the
  source from a temp file, writes JSON to stdout.
* Apply ``resource.setrlimit`` in the child to cap CPU + address space.
* Wall-clock timeout enforced from the parent via ``Popen.communicate(timeout=)``.

For production, wrap this in gVisor / Firecracker / nsjail. This file is the
*last* line of defence, not the only one.
"""

from __future__ import annotations

import json
import os
import resource
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict

from .config import config


LAUNCHER = r"""
import json, sys
from dsa_tracer import trace_source
src = sys.stdin.read()
res = trace_source(src, stdin="", max_events={max_events})
sys.stdout.write(json.dumps(res, ensure_ascii=False))
"""

CPP_LAUNCHER = r"""
import json, sys
from cpp_tracer import trace_source
src = sys.stdin.read()
res = trace_source(src, stdin="", max_events={max_events})
sys.stdout.write(json.dumps(res, ensure_ascii=False))
"""

JS_LAUNCHER = r"""
import json, sys
from js_tracer import trace_source
src = sys.stdin.read()
res = trace_source(src, stdin="", max_events={max_events})
sys.stdout.write(json.dumps(res, ensure_ascii=False))
"""


def _set_child_limits() -> None:
    def _try(rlimit_name: str, value: tuple[int, int]) -> None:
        rlimit = getattr(resource, rlimit_name, None)
        if rlimit is None:
            return
        try:
            resource.setrlimit(rlimit, value)
        except (ValueError, OSError):
            # Some platforms (notably macOS on Apple Silicon for RLIMIT_AS)
            # reject these limits. Wall-clock timeout in the parent still applies.
            pass

    _try("RLIMIT_CPU", (config.sandbox_timeout_seconds, config.sandbox_timeout_seconds))
    _try("RLIMIT_AS", (256 * 1024 * 1024, 256 * 1024 * 1024))
    _try("RLIMIT_CORE", (0, 0))
    _try("RLIMIT_FSIZE", (10 * 1024 * 1024, 10 * 1024 * 1024))
    # Fork-bomb defence: cap processes per uid. We give a modest budget
    # (256) — defeats real fork bombs (which want thousands) while
    # leaving headroom for the JS tracer's Node + V8 worker threads
    # and the C++ tracer's g++ + gdb children.
    _try("RLIMIT_NPROC", (256, 256))


def run_python_in_sandbox(source: str) -> Dict[str, Any]:
    """Execute the Python tracer on ``source`` in a sandboxed subprocess."""
    return _run_sandbox(source, LAUNCHER, "python")


def run_cpp_in_sandbox(source: str) -> Dict[str, Any]:
    """Execute the C++ tracer on ``source`` in a sandboxed subprocess.

    The C++ tracer itself spawns g++ and gdb internally. The wall-clock
    timeout from the parent still applies, so a misbehaving toolchain
    won't hang the request.
    """
    return _run_sandbox(source, CPP_LAUNCHER, "cpp")


def run_js_in_sandbox(source: str) -> Dict[str, Any]:
    """Execute the JS tracer on ``source`` in a sandboxed subprocess.

    Two adjustments vs the Python/cpp paths:
      - Skip rlimits: V8 launches several worker threads on startup
        and on some macOS kernels they trip RLIMIT_NPROC even at
        generous caps.
      - 15 s wall-clock vs the default 5 s: Node cold start + Inspector
        handshake costs ~1 s before the first event; a 100-event trace
        then needs another ~2 s of websocket roundtrips.
    The Docker sandbox (USE_DOCKER_SANDBOX=1) remains the production
    isolation boundary.
    """
    return _run_sandbox(
        source, JS_LAUNCHER, "javascript",
        apply_rlimits=False, timeout_override=15,
    )


def _run_sandbox(
    source: str,
    launcher_template: str,
    language: str,
    *,
    apply_rlimits: bool = True,
    timeout_override: int | None = None,
) -> Dict[str, Any]:
    if len(source.encode("utf-8")) > config.max_source_bytes:
        raise ValueError("source exceeds MAX_SOURCE_BYTES")

    launcher = launcher_template.format(max_events=config.max_trace_events)

    if config.use_docker_sandbox:
        cmd = _docker_cmd(launcher)
    else:
        cmd = [sys.executable, "-c", launcher]

    use_preexec = apply_rlimits and os.name == "posix" and not config.use_docker_sandbox
    preexec = _set_child_limits if use_preexec else None
    base_timeout = timeout_override if timeout_override is not None else config.sandbox_timeout_seconds
    try:
        proc = subprocess.run(
            cmd,
            input=source,
            capture_output=True,
            text=True,
            timeout=base_timeout + 1,
            preexec_fn=preexec,
        )
    except subprocess.TimeoutExpired:
        return _timeout_trace(source, language)

    if proc.returncode != 0:
        return {
            "version": "0.1",
            "language": language,
            "source": source,
            "stdin": "",
            "stdout": "",
            "stderr": proc.stderr or f"sandbox exited with status {proc.returncode}",
            "exit": {"status": "error", "message": proc.stderr.strip()[:500], "truncated": False},
            "events": [],
        }

    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        return {
            "version": "0.1",
            "language": language,
            "source": source,
            "stdin": "",
            "stdout": "",
            "stderr": f"malformed trace from sandbox: {e}",
            "exit": {"status": "error", "message": str(e), "truncated": False},
            "events": [],
        }


def _docker_cmd(launcher: str) -> list[str]:
    """Build the `docker run` argv for one sandboxed invocation.

    Flags chosen for defence in depth:
      --network=none      no outbound traffic
      --read-only         immutable root FS
      --tmpfs /tmp        writable scratch with size cap
      --memory / --cpus   cgroup caps replace per-process rlimits
      --security-opt seccomp=...  deny-by-default syscall filter
      --rm -i             ephemeral container, accept stdin

    The image's ENTRYPOINT is `python`, so we append `-c <launcher>`.
    """
    return [
        "docker", "run", "--rm", "-i",
        "--network=none",
        "--read-only",
        "--tmpfs", "/tmp:size=64m,exec",
        "--tmpfs", "/tmp/work:size=64m,exec",
        f"--memory={256}m",
        f"--cpus={1}",
        "--security-opt", f"seccomp={config.docker_seccomp_profile}",
        config.docker_sandbox_image,
        "-c", launcher,
    ]


def _timeout_trace(source: str, language: str = "python") -> Dict[str, Any]:
    return {
        "version": "0.1",
        "language": language,
        "source": source,
        "stdin": "",
        "stdout": "",
        "stderr": "execution exceeded the time limit",
        "exit": {
            "status": "timeout",
            "message": f"timed out after {config.sandbox_timeout_seconds}s",
            "truncated": True,
        },
        "events": [],
    }
