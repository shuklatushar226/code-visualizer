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
        return raw.get("payload", {}).get("value", "")

    # ---------------------------------------------------------------- #
    # internals
    # ---------------------------------------------------------------- #

    def _send(self, cmd: str) -> Optional[Dict[str, Any]]:
        """Send a GDB/MI command and return the result record, if any."""
        responses = self._gdb.write(cmd)
        for r in responses:
            if r.get("type") == "result":
                return r
        return None


def compile_cpp(source_path: str, output_path: Optional[str] = None) -> str:
    """Compile a C++ source file to a debuggable binary."""
    if output_path is None:
        output_path = str(Path(tempfile.mkdtemp()) / "user.bin")
    cmd = ["g++", "-std=c++17", "-g", "-O0", "-o", output_path, source_path]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"compilation failed:\n{proc.stderr}")
    return output_path
