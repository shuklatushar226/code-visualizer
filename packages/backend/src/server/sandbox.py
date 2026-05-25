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


def _set_child_limits() -> None:
    # CPU seconds.
    resource.setrlimit(resource.RLIMIT_CPU, (config.sandbox_timeout_seconds, config.sandbox_timeout_seconds))
    # Address space (256 MiB).
    resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
    # No core dumps.
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    # File size (10 MiB).
    resource.setrlimit(resource.RLIMIT_FSIZE, (10 * 1024 * 1024, 10 * 1024 * 1024))


def run_python_in_sandbox(source: str) -> Dict[str, Any]:
    """Execute the Python tracer on ``source`` in a sandboxed subprocess.

    Returns the parsed trace dict. Raises on hard failures.
    """
    if len(source.encode("utf-8")) > config.max_source_bytes:
        raise ValueError("source exceeds MAX_SOURCE_BYTES")

    launcher = LAUNCHER.format(max_events=config.max_trace_events)

    # We pipe both: launcher via -c, source via stdin.
    cmd = [sys.executable, "-S", "-I", "-c", launcher]

    try:
        proc = subprocess.run(
            cmd,
            input=source,
            capture_output=True,
            text=True,
            timeout=config.sandbox_timeout_seconds + 1,
            preexec_fn=_set_child_limits if os.name == "posix" else None,
        )
    except subprocess.TimeoutExpired:
        return _timeout_trace(source)

    if proc.returncode != 0:
        # Tracer itself crashed — surface as an error trace.
        return {
            "version": "0.1",
            "language": "python",
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
            "language": "python",
            "source": source,
            "stdin": "",
            "stdout": "",
            "stderr": f"malformed trace from sandbox: {e}",
            "exit": {"status": "error", "message": str(e), "truncated": False},
            "events": [],
        }


def _timeout_trace(source: str) -> Dict[str, Any]:
    return {
        "version": "0.1",
        "language": "python",
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
