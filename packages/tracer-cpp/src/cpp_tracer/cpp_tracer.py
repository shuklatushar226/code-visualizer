"""Translate GDB stepping into Trace Event Protocol JSON.

This module is the **C++ analogue of tracer-python**. It is currently a
skeleton: the high-level loop is implemented, but the value-encoding
functions are TODOs because they require GDB pretty-printers (or libstdc++
internals) to do well.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from .gdb_driver import GdbDriver, compile_cpp


def trace_source(source: str, stdin: str = "", max_events: int = 5000) -> Dict[str, Any]:
    """Compile + step a C++ program, emitting a Trace Event Protocol doc.

    Currently raises NotImplementedError for value encoding. Returning here
    so the high-level shape of the function is visible.
    """
    # 1. Write source to a temp file.
    import tempfile

    work = Path(tempfile.mkdtemp())
    src_path = work / "main.cpp"
    src_path.write_text(source, encoding="utf-8")

    # 2. Compile.
    try:
        binary = compile_cpp(str(src_path), str(work / "main.bin"))
    except RuntimeError as e:
        return _err_result(source, stdin, str(e))

    # 3. Drive GDB.
    drv = GdbDriver(binary)
    events: List[dict] = []
    try:
        drv.run_to_main()
        for _ in range(max_events):
            frames = drv.stack_frames()
            if not frames:
                break
            top = frames[0]
            line = int(top.get("line", 0)) if top.get("line") else 0
            event = {
                "t": len(events),
                "kind": "step",
                "line": line,
                "file": top.get("fullname", top.get("file", "main.cpp")),
                "stack": _encode_stack(drv, frames),
                "heap": {},  # TODO: extract heap objects via -data-evaluate-expression
                "stdout_delta": None,
                "exception": None,
            }
            events.append(event)
            try:
                drv.next()
            except Exception:
                break
    finally:
        drv.quit()

    return {
        "version": "0.1",
        "language": "cpp",
        "source": source,
        "stdin": stdin,
        "stdout": "",
        "stderr": "",
        "exit": {"status": "ok", "message": None, "truncated": len(events) >= max_events},
        "events": events,
    }


# ---------------------------------------------------------------------- #
# encoding helpers (skeleton — these are the meat of M3)
# ---------------------------------------------------------------------- #

def _encode_stack(drv: GdbDriver, frames: List[dict]) -> List[dict]:
    out = []
    for i, f in enumerate(frames):
        raw_locals = drv.locals_in_frame(i)
        # TODO: parse each value string into a protocol Value.
        # For now, store the raw string so the front-end at least shows
        # something during early development.
        out.append({
            "func": f.get("func", "?"),
            "file": f.get("fullname", f.get("file", "?")),
            "line": int(f.get("line", 0)) if f.get("line") else 0,
            "locals": {k: {"kind": "str", "v": v} for k, v in raw_locals.items()},
            "args": [],
        })
    return out


def _err_result(source: str, stdin: str, msg: str) -> Dict[str, Any]:
    return {
        "version": "0.1",
        "language": "cpp",
        "source": source,
        "stdin": stdin,
        "stdout": "",
        "stderr": msg,
        "exit": {"status": "error", "message": msg, "truncated": False},
        "events": [],
    }
