"""Translate GDB stepping into Trace Event Protocol JSON.

Architecture (M3 minimum):
  1. Compile user source with -g -O0 to a temp binary.
  2. Scan symbols for ``__viz_<TYPE>_<key>`` to build a VizCatalog from the
     macros in ``<viz.hpp>``.
  3. Run the binary under GDB/MI, stepping one source line at a time.
  4. At each step, walk the call stack, decode each local's value via the
     helpers in values.py, and emit a TraceEvent.

This implementation is intentionally narrow: primitives + pointers + the
annotated-struct case round-trip cleanly; anything else falls back to
``{"kind": "str", "v": <raw>}`` so the front-end still has something to
render. Improving fidelity beyond this is in scope for a follow-up.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .gdb_driver import GdbDriver, compile_cpp
from .values import (
    VizAnnotation,
    VizCatalog,
    parse_pointer,
    parse_scalar,
    parse_struct_fields,
)


def trace_source(source: str, stdin: str = "", max_events: int = 5000) -> Dict[str, Any]:
    """Compile + step a C++ program, emitting a Trace Event Protocol doc."""
    work = Path(tempfile.mkdtemp(prefix="dsaviz-cpp-"))
    src_path = work / "main.cpp"
    src_path.write_text(source, encoding="utf-8")

    # Allow the user to include "viz.hpp" by passing the header's location.
    viz_dir = Path(__file__).resolve().parent.parent.parent / "include"
    compile_args = [f"-I{viz_dir}"] if viz_dir.exists() else []

    try:
        binary = compile_cpp(str(src_path), str(work / "main.bin"), extra_args=compile_args)
    except RuntimeError as e:
        return _err_result(source, stdin, str(e))

    catalog = _build_catalog(binary)

    if not shutil.which("gdb"):
        return _err_result(
            source,
            stdin,
            "gdb is not installed in this environment; C++ tracing requires gdb on PATH.",
        )

    drv = GdbDriver(binary)
    events: List[dict] = []
    heap: Dict[str, Dict[str, Any]] = {}
    addr_to_id: Dict[str, str] = {}
    truncated = False
    stdout_acc = ""

    try:
        drv.run_to_main()
        for _ in range(max_events):
            frames = drv.stack_frames()
            if not frames:
                break
            top = frames[0]
            line = int(top.get("line", 0)) if top.get("line") else 0
            stack_repr = _encode_stack(drv, frames, heap, addr_to_id, catalog)
            event = {
                "t": len(events),
                "kind": "step",
                "line": line,
                "file": top.get("fullname", top.get("file", "main.cpp")),
                "stack": stack_repr,
                "heap": dict(heap),
                "stdout_delta": None,
                "exception": None,
            }
            events.append(event)
            try:
                drv.next()
            except Exception:
                break
        else:
            truncated = True
    finally:
        drv.quit()

    return {
        "version": "0.1",
        "language": "cpp",
        "source": source,
        "stdin": stdin,
        "stdout": stdout_acc,
        "stderr": "",
        "exit": {"status": "ok", "message": None, "truncated": truncated},
        "events": events,
    }


# ---------------------------------------------------------------------- #
# Symbol catalog
# ---------------------------------------------------------------------- #

def _build_catalog(binary: str) -> VizCatalog:
    """Run `nm` to find __viz_<TYPE>_<key> symbols left by VIZ_REGISTER_*."""
    try:
        out = subprocess.run(
            ["nm", "-g", binary], capture_output=True, text=True, check=False, timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return VizCatalog()
    symbols = []
    for line in out.stdout.splitlines():
        m = re.search(r"\b(__viz_[A-Za-z0-9_]+)\b", line)
        if m:
            symbols.append(m.group(1))
    return VizCatalog.from_symbol_strings(symbols)


# ---------------------------------------------------------------------- #
# Stack + local encoding
# ---------------------------------------------------------------------- #

def _encode_stack(
    drv: GdbDriver,
    frames: List[dict],
    heap: Dict[str, Dict[str, Any]],
    addr_to_id: Dict[str, str],
    catalog: VizCatalog,
) -> List[dict]:
    """Convert frames into protocol Frame dicts, decoding locals as we go."""
    out: List[dict] = []
    for i, f in enumerate(frames):
        raw_locals = drv.locals_in_frame(i)
        decoded: Dict[str, Any] = {}
        for name, raw in raw_locals.items():
            decoded[name] = _decode_value(drv, name, raw, heap, addr_to_id, catalog)
        out.append({
            "func": f.get("func", "?"),
            "file": f.get("fullname", f.get("file", "?")),
            "line": int(f.get("line", 0)) if f.get("line") else 0,
            "locals": decoded,
            "args": [],
        })
    return out


def _decode_value(
    drv: GdbDriver,
    expr: str,
    raw: str,
    heap: Dict[str, Dict[str, Any]],
    addr_to_id: Dict[str, str],
    catalog: VizCatalog,
) -> Dict[str, Any]:
    """Decode one local into a protocol Value, expanding heap as needed."""
    scalar = parse_scalar(raw)
    if scalar is not None:
        return scalar

    # Pointer-shaped output: "0xADDR <symbol>" or "0xADDR ..."
    addr = parse_pointer(raw)
    if addr:
        ref_id = _alloc_id(addr, addr_to_id)
        if ref_id not in heap:
            heap[ref_id] = _decode_struct_at(drv, expr, addr, heap, addr_to_id, catalog)
        return {"kind": "ref", "id": ref_id}

    # Brace-wrapped struct literal
    fields = parse_struct_fields(raw)
    if fields is not None:
        # Pretend the struct lives on the heap (synthetic id) so the protocol
        # can carry it; the front-end renders it via the generic object view.
        synthetic_id = f"h_struct_{len(heap)}"
        heap[synthetic_id] = _struct_to_heap_object(drv, "object", fields, heap, addr_to_id, catalog)
        return {"kind": "ref", "id": synthetic_id}

    # Fallback: opaque string. Trim to schema's 1 KiB cap.
    return {"kind": "str", "v": raw[:1024]}


def _alloc_id(addr: str, addr_to_id: Dict[str, str]) -> str:
    if addr in addr_to_id:
        return addr_to_id[addr]
    new_id = f"h_{len(addr_to_id)}"
    addr_to_id[addr] = new_id
    return new_id


def _decode_struct_at(
    drv: GdbDriver,
    expr: str,
    addr: str,
    heap: Dict[str, Dict[str, Any]],
    addr_to_id: Dict[str, str],
    catalog: VizCatalog,
) -> Dict[str, Any]:
    """Dereference a pointer expression and decode the pointee."""
    deref = drv.evaluate(f"*({expr})")
    type_str = drv.type_of(expr) or ""
    type_name = _strip_pointer_type(type_str)
    fields = parse_struct_fields(deref) or {}
    return _struct_to_heap_object(drv, type_name, fields, heap, addr_to_id, catalog)


def _struct_to_heap_object(
    drv: GdbDriver,
    type_name: str,
    fields: Dict[str, str],
    heap: Dict[str, Dict[str, Any]],
    addr_to_id: Dict[str, str],
    catalog: VizCatalog,
) -> Dict[str, Any]:
    """Decode a struct's fields into a protocol HeapObject.

    If the catalog has a VIZ_REGISTER_* entry for this type, narrow the
    emitted fields to the annotated ones (val/next/prev for linked_list,
    val/left/right for tree, adj for graph). The front-end's
    `detectStructure` recognises these shapes by field name + class name,
    so emitting only the annotated fields keeps the renderer choice
    unambiguous.
    """
    annotation = catalog.get(type_name) if type_name else None
    if annotation is not None:
        keep: List[str] = [f for f in (
            annotation.val_field,
            annotation.next_field,
            annotation.left_field,
            annotation.right_field,
            annotation.adj_field,
        ) if f]
        narrowed: Dict[str, str] = {k: v for k, v in fields.items() if k in keep}
        # Preserve order matching VIZ_REGISTER_* so the front-end sees
        # `val` before `next` (its heuristic prefers that).
        ordered = {k: narrowed[k] for k in keep if k in narrowed}
        decoded_fields = {
            fname: _decode_value(drv, fname, fraw, heap, addr_to_id, catalog)
            for fname, fraw in ordered.items()
        }
    else:
        decoded_fields = {
            fname: _decode_value(drv, fname, fraw, heap, addr_to_id, catalog)
            for fname, fraw in fields.items()
        }
    return {
        "kind": "object",
        "type": type_name or "object",
        "fields": decoded_fields,
    }


def _strip_pointer_type(type_str: str) -> str:
    # GDB reports types like "Node *" — strip trailing pointer indicators.
    return re.sub(r"\s*\*+\s*$", "", type_str.strip())


# ---------------------------------------------------------------------- #
# Error helper
# ---------------------------------------------------------------------- #

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
