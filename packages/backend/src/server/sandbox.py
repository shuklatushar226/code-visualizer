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
import signal
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict

from .config import config


# The user's source code is piped over the child's stdin, so the user's
# program stdin is delivered out-of-band: embedded into the launcher as a
# Python string literal via {stdin!r} (repr safely escapes any input).
# json.dumps uses allow_nan=False so a stray non-finite float fails loudly
# inside the sandbox instead of producing Infinity/NaN tokens that crash the
# parent's strict-JSON response serialization.
LAUNCHER = r"""
import json, sys
from dsa_tracer import trace_source
src = sys.stdin.read()
res = trace_source(src, stdin={stdin!r}, max_events={max_events})
sys.stdout.write(json.dumps(res, ensure_ascii=False, allow_nan=False))
"""

CPP_LAUNCHER = r"""
import json, sys
from cpp_tracer import trace_source
src = sys.stdin.read()
res = trace_source(src, stdin={stdin!r}, max_events={max_events})
sys.stdout.write(json.dumps(res, ensure_ascii=False, allow_nan=False))
"""

JS_LAUNCHER = r"""
import json, sys
from js_tracer import trace_source
src = sys.stdin.read()
res = trace_source(src, stdin={stdin!r}, max_events={max_events})
sys.stdout.write(json.dumps(res, ensure_ascii=False, allow_nan=False))
"""

JAVA_LAUNCHER = r"""
import json, sys
from java_tracer import trace_source
src = sys.stdin.read()
res = trace_source(src, stdin={stdin!r}, max_events={max_events})
sys.stdout.write(json.dumps(res, ensure_ascii=False, allow_nan=False))
"""

# Only these environment keys are passed to the sandboxed child. This keeps
# process secrets (e.g. DSA_VIZ_AI_KEY, cloud credentials) out of untrusted
# code while preserving what the interpreter and toolchains genuinely need.
_SAFE_CHILD_ENV_KEYS = (
    "PATH", "HOME", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR", "TEMP", "TMP",
    "SYSTEMROOT", "PATHEXT",
)


def _child_env() -> Dict[str, str]:
    return {k: os.environ[k] for k in _SAFE_CHILD_ENV_KEYS if k in os.environ}


def _set_limits(*, address_space: bool, process_count: bool) -> None:
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
    if address_space:
        _try("RLIMIT_AS", (256 * 1024 * 1024, 256 * 1024 * 1024))
    _try("RLIMIT_CORE", (0, 0))
    _try("RLIMIT_FSIZE", (10 * 1024 * 1024, 10 * 1024 * 1024))
    # RLIMIT_NPROC counts every process owned by this numeric UID on the host,
    # including unrelated containers on some PaaS hosts. Allow those platforms
    # to disable it and rely on their container/cgroup process ceiling instead.
    if process_count and config.max_child_processes > 0:
        _try(
            "RLIMIT_NPROC",
            (config.max_child_processes, config.max_child_processes),
        )


def _set_child_limits() -> None:
    _set_limits(address_space=True, process_count=True)


def _set_cpp_child_limits() -> None:
    # GDB and the debuggee need more virtual address space than the Python
    # tracer, and GDB spawns helper processes. Retain CPU/file/core limits;
    # the service container supplies the memory and process ceilings.
    _set_limits(address_space=False, process_count=False)


def run_python_in_sandbox(source: str, stdin: str = "") -> Dict[str, Any]:
    """Execute the Python tracer on ``source`` in a sandboxed subprocess."""
    return _run_sandbox(source, LAUNCHER, "python", stdin=stdin)


def run_cpp_in_sandbox(source: str, stdin: str = "") -> Dict[str, Any]:
    """Execute the C++ tracer on ``source`` in a sandboxed subprocess.

    The C++ tracer itself spawns g++ and gdb internally. The wall-clock
    timeout from the parent still applies, so a misbehaving toolchain
    won't hang the request.
    """
    return _run_sandbox(
        source,
        CPP_LAUNCHER,
        "cpp",
        stdin=stdin,
        limit_setter=_set_cpp_child_limits,
        timeout_override=config.cpp_timeout_seconds,
    )


def run_js_in_sandbox(source: str, stdin: str = "") -> Dict[str, Any]:
    """Execute the JS tracer on ``source`` in a sandboxed subprocess.

    Two adjustments vs the Python/cpp paths:
      - Skip rlimits: V8 launches several worker threads on startup
        and on some macOS kernels they trip RLIMIT_NPROC even at
        generous caps.
      - A larger wall-clock budget than Python: Node cold start + Inspector
        handshake costs ~1 s before the first event; a 100-event trace
        then needs another ~2 s of websocket roundtrips.
    The Docker sandbox (USE_DOCKER_SANDBOX=1) remains the production
    isolation boundary.
    """
    return _run_sandbox(
        source, JS_LAUNCHER, "javascript",
        stdin=stdin,
        limit_setter=None,
        timeout_override=config.javascript_timeout_seconds,
    )


def run_java_in_sandbox(source: str, stdin: str = "") -> Dict[str, Any]:
    """Execute the Java tracer on ``source`` in a sandboxed subprocess.

    Like the JS path, rlimits are skipped (the JDK launches many threads, and
    the tracer itself spawns javac + two JVMs — the debugger and the debuggee —
    which would trip RLIMIT_NPROC). The wall-clock budget is larger because
    those steps are slow; the java_tracer wrapper also enforces its own javac
    and run timeouts and kills the debuggee's process group, so this outer
    timeout is only a last-resort backstop.
    """
    return _run_sandbox(
        source, JAVA_LAUNCHER, "java",
        stdin=stdin, limit_setter=None, timeout_override=45,
    )


def _run_sandbox(
    source: str,
    launcher_template: str,
    language: str,
    *,
    stdin: str = "",
    limit_setter: Callable[[], None] | None = _set_child_limits,
    timeout_override: int | None = None,
) -> Dict[str, Any]:
    if len(source.encode("utf-8")) > config.max_source_bytes:
        raise ValueError("source exceeds MAX_SOURCE_BYTES")

    launcher = launcher_template.format(max_events=config.max_trace_events, stdin=stdin)

    if config.use_docker_sandbox:
        cmd = _docker_cmd(launcher)
        child_env = None  # the container starts from a clean environment
    else:
        # -I: isolated mode (ignore PYTHON* env vars and user site-packages).
        # env: a scrubbed allowlist so untrusted code can't read process secrets.
        cmd = [sys.executable, "-I", "-c", launcher]
        child_env = _child_env()

    use_preexec = limit_setter is not None and os.name == "posix" and not config.use_docker_sandbox
    preexec = limit_setter if use_preexec else None
    base_timeout = timeout_override if timeout_override is not None else config.sandbox_timeout_seconds
    # Put each non-container execution in its own process group. Without this,
    # killing the tracer on timeout leaves user-spawned children running.
    start_new_session = os.name == "posix" and not config.use_docker_sandbox
    creationflags = 0
    if os.name == "nt" and not config.use_docker_sandbox:
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        preexec_fn=preexec,
        env=child_env,
        start_new_session=start_new_session,
        creationflags=creationflags,
    )
    try:
        stdout, stderr = proc.communicate(input=source, timeout=base_timeout + 1)
    except subprocess.TimeoutExpired:
        _terminate_process_tree(proc)
        proc.communicate()  # reap the direct child and drain its pipes
        return _timeout_trace(source, language, timeout_seconds=base_timeout)
    # A submission may intentionally leave background children behind even
    # when the tracer exits normally or is stopped by an rlimit.
    _terminate_process_tree(proc)

    if proc.returncode != 0:
        return {
            "version": "0.1",
            "language": language,
            "source": source,
            "stdin": stdin,
            "stdout": "",
            "stderr": stderr or f"sandbox exited with status {proc.returncode}",
            "exit": {"status": "error", "message": stderr.strip()[:500], "truncated": False},
            "events": [],
        }

    try:
        return json.loads(stdout)
    except json.JSONDecodeError as e:
        return {
            "version": "0.1",
            "language": language,
            "source": source,
            "stdin": stdin,
            "stdout": "",
            "stderr": f"malformed trace from sandbox: {e}",
            "exit": {"status": "error", "message": str(e), "truncated": False},
            "events": [],
        }


def _terminate_process_tree(proc: subprocess.Popen[str]) -> None:
    """Best-effort termination of a timed-out tracer and its descendants."""
    if os.name == "posix" and not config.use_docker_sandbox:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
            return
        except ProcessLookupError:
            return
        except OSError:
            pass
    if proc.poll() is None:
        proc.kill()


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


def _timeout_trace(
    source: str, language: str = "python", *, timeout_seconds: int | None = None
) -> Dict[str, Any]:
    seconds = timeout_seconds if timeout_seconds is not None else config.sandbox_timeout_seconds
    return {
        "version": "0.1",
        "language": language,
        "source": source,
        "stdin": "",
        "stdout": "",
        "stderr": "execution exceeded the time limit",
        "exit": {
            "status": "timeout",
            "message": f"timed out after {seconds}s",
            "truncated": True,
        },
        "events": [],
    }
