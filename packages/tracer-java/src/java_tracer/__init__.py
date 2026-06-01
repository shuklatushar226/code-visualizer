"""java_tracer — produce Trace Event Protocol JSON from Java source via JDI.

Strategy (mirrors the C++ tracer's "orchestrate an external debugger" shape):

* Detect the user's class name and compile the source with ``javac -g`` (debug
  info is required for JDI to read locals and line numbers).
* Launch the compiled class under a small JDI helper — ``helper/dsaviz/Tracer.java``
  — which single-steps the program (restricted to user code), decodes locals and
  the reachable object graph using JDI's typed value API, and writes the complete
  Trace Event Protocol document to stdout. The helper is compiled once and cached.
* The user's stdin is relayed to the debuggee through the helper; the helper's
  stdout (the JSON) is captured here and the ``source``/``stdin`` fields filled in.

This module is the sole wall-clock authority: it runs ``java`` in its own process
group and kills the whole group on timeout so the debuggee JVM can't be orphaned.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

__all__ = ["trace_source"]
__version__ = "0.1.0"

# helper/dsaviz/Tracer.java is a sibling of src/ (same mechanism the C++ tracer
# uses to locate its bundled include/viz.hpp).
_HELPER_SRC = Path(__file__).resolve().parent.parent.parent / "helper" / "dsaviz" / "Tracer.java"

_JAVAC_TIMEOUT = 20
_RUN_TIMEOUT = 20

_TYPE_RE = re.compile(
    r"(?m)^[ \t]*(public\s+)?(?:final\s+|abstract\s+|sealed\s+|non-sealed\s+|strictfp\s+)*"
    r"(class|interface|enum|record)\s+([A-Za-z_]\w*)"
)
_MAIN_RE = re.compile(r"public\s+static\s+void\s+main\s*\(\s*(?:final\s+)?String")
_PACKAGE_RE = re.compile(r"(?m)^\s*package\s+([\w.]+)\s*;")


def trace_source(source: str, stdin: str = "", max_events: int = 5000) -> Dict[str, Any]:
    if not (shutil.which("javac") and shutil.which("java")):
        return _err(source, stdin, "Java tracing requires a JDK (javac + java) on PATH.")

    detected, derr = _detect_classes(source)
    if derr:
        return _err(source, stdin, derr)
    pkg, launch_class, public_name = detected

    work = Path(tempfile.mkdtemp(prefix="dsaviz-java-"))
    try:
        classes = work / "classes"
        classes.mkdir()
        src_path = _write_source(work, source, pkg, public_name)

        cc = subprocess.run(
            ["javac", "-g", "-encoding", "UTF-8", "-d", str(classes), str(src_path)],
            capture_output=True,
            text=True,
            timeout=_JAVAC_TIMEOUT,
        )
        if cc.returncode != 0:
            return _err(source, stdin, f"compilation failed:\n{(cc.stderr or '').strip()}")

        helper_dir = _ensure_helper_compiled()
        if helper_dir is None:
            return _err(source, stdin, "failed to compile the Java tracer helper.")

        classpath = os.pathsep.join([helper_dir, str(classes)])
        cmd = [
            "java", "-cp", classpath, "dsaviz.Tracer",
            "--main", launch_class,
            "--cp", str(classes),
            "--max-events", str(max_events),
            "--source-file", f"{public_name}.java",
        ]
        rc, out, err, timed_out = _run_group(cmd, stdin, _RUN_TIMEOUT)
        if timed_out:
            return _timeout(source, stdin)
        if not (out or "").strip():
            msg = (err or "").strip()[:500] or f"tracer exited with status {rc}"
            return _err(source, stdin, msg)
        try:
            doc = json.loads(out)
        except json.JSONDecodeError as e:
            return _err(source, stdin, f"malformed trace from helper: {e}")
        # The helper has no access to the original source text or stdin; fill them in.
        doc["source"] = source
        doc["stdin"] = stdin
        return doc
    finally:
        shutil.rmtree(work, ignore_errors=True)


# --------------------------------------------------------------------------- #
# class detection
# --------------------------------------------------------------------------- #

def _detect_classes(source: str) -> Tuple[Optional[Tuple[str, str, str]], Optional[str]]:
    """Return ((package, launch_class_fqn, public_simple_name), None) or (None, error)."""
    types = list(_TYPE_RE.finditer(source))
    if not types:
        return None, "no class declaration found; define a class with a `main` method."
    if not _MAIN_RE.search(source):
        return None, "no `public static void main(String[])` found; add a main method to trace."

    pkg_m = _PACKAGE_RE.search(source)
    pkg = pkg_m.group(1) if pkg_m else ""

    publics = [m.group(3) for m in types if m.group(1)]
    # Java requires the file to be named after the public top-level type; the
    # launch class is conventionally that same public class (which holds main).
    public_name = publics[0] if publics else types[0].group(3)
    launch_class = f"{pkg}.{public_name}" if pkg else public_name
    return (pkg, launch_class, public_name), None


def _write_source(work: Path, source: str, pkg: str, public_name: str) -> Path:
    src_dir = work / "src"
    if pkg:
        src_dir = src_dir.joinpath(*pkg.split("."))
    src_dir.mkdir(parents=True, exist_ok=True)
    path = src_dir / f"{public_name}.java"
    path.write_text(source, encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# helper compilation (cached, keyed by content hash)
# --------------------------------------------------------------------------- #

def _ensure_helper_compiled() -> Optional[str]:
    if not _HELPER_SRC.exists():
        return None
    digest = hashlib.sha256(_HELPER_SRC.read_bytes()).hexdigest()[:16]
    base = Path(tempfile.gettempdir()) / "dsaviz-java-helper" / digest
    marker = base / "dsaviz" / "Tracer.class"
    if marker.exists():
        return str(base)
    base.mkdir(parents=True, exist_ok=True)
    cc = subprocess.run(
        ["javac", "-d", str(base), str(_HELPER_SRC)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if cc.returncode != 0 or not marker.exists():
        return None
    return str(base)


# --------------------------------------------------------------------------- #
# subprocess execution with process-group kill on timeout
# --------------------------------------------------------------------------- #

def _run_group(cmd, stdin: str, timeout: int) -> Tuple[int, str, str, bool]:
    """Run ``cmd`` in its own process group; on timeout kill the whole group so
    the JDI-launched debuggee JVM is never orphaned. Returns
    (returncode, stdout, stderr, timed_out)."""
    posix = os.name == "posix"
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=posix,
    )
    try:
        out, err = proc.communicate(input=stdin, timeout=timeout)
        return proc.returncode, out, err, False
    except subprocess.TimeoutExpired:
        if posix:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception:
                proc.kill()
        else:
            proc.kill()
        try:
            proc.communicate(timeout=5)
        except Exception:
            pass
        return -1, "", "", True


# --------------------------------------------------------------------------- #
# error / timeout envelopes
# --------------------------------------------------------------------------- #

def _envelope(source: str, stdin: str, status: str, message: str, truncated: bool = False) -> Dict[str, Any]:
    return {
        "version": "0.1",
        "language": "java",
        "source": source,
        "stdin": stdin,
        "stdout": "",
        "stderr": message,
        "exit": {"status": status, "message": message, "truncated": truncated},
        "events": [],
    }


def _err(source: str, stdin: str, message: str) -> Dict[str, Any]:
    return _envelope(source, stdin, "error", message)


def _timeout(source: str, stdin: str) -> Dict[str, Any]:
    return _envelope(source, stdin, "timeout", "execution exceeded the time limit", truncated=True)
