"""Thin wrapper over pygdbmi to step a C++ binary.

This is intentionally minimal — it shows the GDB/MI commands we'd issue and
gives a clean Python surface so `cpp_tracer.py` can focus on protocol
translation.

Status: skeleton. Methods that aren't implemented raise NotImplementedError.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional


class GdbDriver:
    def __init__(self, binary_path: str) -> None:
        try:
            from pygdbmi.gdbcontroller import GdbController  # type: ignore
        except ImportError as e:  # pragma: no cover
            raise RuntimeError(
                "pygdbmi is required for the C++ tracer. Install it with "
                "`pip install pygdbmi`."
            ) from e

        self._gdb = GdbController()
        self._binary = binary_path
        self._send(f"-file-exec-and-symbols {binary_path}")
        # Pretty-printing is a prerequisite for the var-object walker to see
        # STL containers as their logical children (vector of N) instead of
        # their internal _M_impl fields. libstdc++ ≥10 auto-loads its
        # printers; this is belt-and-suspenders for older distros.
        self._send("-gdb-set print pretty on")
        self._send("-gdb-set print object on")
        self._var_counter = 0

    # ---------------------------------------------------------------- #
    # session control
    # ---------------------------------------------------------------- #

    def run_to_main(self) -> None:
        self._send("-break-insert main")
        self._send("-exec-run")

    def step(self) -> None:
        """Single-step one source line."""
        self._send("-exec-step")

    def next(self) -> None:
        """Step over function calls."""
        self._send("-exec-next")

    def continue_(self) -> None:
        self._send("-exec-continue")

    def quit(self) -> None:
        try:
            self._gdb.exit()
        except Exception:
            pass

    # ---------------------------------------------------------------- #
    # introspection
    # ---------------------------------------------------------------- #

    def stack_frames(self) -> List[Dict[str, Any]]:
        """Return the current call stack (bottom-of-stack first)."""
        raw = self._send("-stack-list-frames")
        # TODO: parse raw["payload"]["stack"] into a uniform format
        return raw.get("payload", {}).get("stack", []) if raw else []

    def locals_in_frame(self, frame_idx: int) -> Dict[str, str]:
        """Return a dict of local-name → raw value-string for one frame."""
        self._send(f"-stack-select-frame {frame_idx}")
        raw = self._send("-stack-list-locals 2")  # 2 = name+value
        out: Dict[str, str] = {}
        for local in raw.get("payload", {}).get("locals", []) if raw else []:
            out[local["name"]] = local.get("value", "")
        return out

    def evaluate(self, expr: str) -> str:
        """Evaluate a C++ expression in the current frame."""
        raw = self._send(f"-data-evaluate-expression {expr!r}")
        return raw.get("payload", {}).get("value", "") if raw else ""

    def type_of(self, expr: str) -> Optional[str]:
        """Return the textual type of an expression, or None on failure.

        `whatis` produces a `console`-stream record like ``~"type = Node *\\n"``
        followed by an empty result. We have to scan *all* responses, not
        just the result channel, to recover the type string.
        """
        records = self._send_all(f"whatis {expr}")
        for r in records:
            if r.get("type") != "console":
                continue
            payload = r.get("payload")
            if not isinstance(payload, str):
                continue
            txt = payload.replace("\\n", "").strip()
            if "type =" in txt:
                return txt.split("type =", 1)[1].strip().rstrip(";")
        return None

    # ---------------------------------------------------------------- #
    # variable objects — the STL walker
    # ---------------------------------------------------------------- #

    def var_create(self, expr: str) -> Optional[Dict[str, Any]]:
        """Create a GDB/MI variable object for `expr`.

        Returns a dict like ``{"name": "vN", "numchild": "4", "type": "..."}``
        (gdb returns numchild as a string; the caller should coerce). Returns
        None if creation fails (e.g. expr unevaluable in current frame).

        Variable objects are gdb's IDE-friendly walker: every container's
        children are exposed as named sub-objects with their own types,
        which is how pygdbmi-driven IDEs like VS Code's cpptools render
        std::vector et al without parsing pretty-printer text.
        """
        self._var_counter += 1
        name = f"v{self._var_counter}"
        # `*` = floating frame (auto-track current frame).
        raw = self._send(f"-var-create {name} * {expr}")
        if not raw or raw.get("message") == "error":
            return None
        payload = raw.get("payload") or {}
        payload["name"] = name
        return payload

    def var_list_children(self, var_name: str) -> List[Dict[str, Any]]:
        """List the children of a variable object created by var_create.

        Each child is a dict with at least ``name``, ``exp``, ``numchild``,
        and (for primitive leaves) ``value``. Non-primitive children require
        another var-create on their ``exp`` to expand.

        `--all-values` asks gdb to include the formatted value for primitive
        children inline, so simple types come back in one round-trip.
        """
        raw = self._send(f"-var-list-children --all-values {var_name}")
        if not raw:
            return []
        payload = raw.get("payload") or {}
        return payload.get("children", []) or []

    def var_delete(self, var_name: str) -> None:
        """Tear down a variable object. Safe to call on a None / missing name."""
        if not var_name:
            return
        self._send(f"-var-delete {var_name}")

    # ---------------------------------------------------------------- #
    # internals
    # ---------------------------------------------------------------- #

    def _send(self, cmd: str) -> Optional[Dict[str, Any]]:
        """Send a GDB/MI command and return the first result record, if any."""
        for r in self._send_all(cmd):
            if r.get("type") == "result":
                return r
        return None

    def _send_all(self, cmd: str) -> List[Dict[str, Any]]:
        """Send a GDB/MI command and return *all* response records.

        GDB/MI sends a mix of channels per command — `result` (the final
        machine-readable record), `console` (`~` stream), `log` (`&` stream),
        `notify`, and `target`. Some commands (notably `whatis`) put their
        useful output on the console stream and the result is empty.
        """
        return self._gdb.write(cmd) or []


def compile_cpp(
    source_path: str,
    output_path: Optional[str] = None,
    extra_args: Optional[List[str]] = None,
) -> str:
    """Compile a C++ source file to a debuggable binary."""
    if output_path is None:
        output_path = str(Path(tempfile.mkdtemp()) / "user.bin")
    cmd = ["g++", "-std=c++17", "-g", "-O0"]
    if extra_args:
        cmd.extend(extra_args)
    cmd.extend(["-o", output_path, source_path])
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"compilation failed:\n{proc.stderr}")
    return output_path
