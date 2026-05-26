"""js_tracer — V8 Inspector-driven JavaScript tracer.

Spawns `node --inspect-brk` on the user's source, attaches via the
V8 Inspector Protocol over a websocket, steps one paused-event at a
time, and emits a Trace Event Protocol document identical in shape
to what tracer-python and tracer-cpp produce.

Public surface is a single synchronous `trace_source(src, stdin,
max_events) → dict`. Internally the orchestrator is async (websocket
+ subprocess); `asyncio.run` wraps the entry so the backend's sync
sandbox launcher can call it directly.
"""
from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from .inspector import InspectorError, InspectorSession, spawn_node_inspector
from .values import alloc_id, encode_remote_object

__version__ = "0.1.0"

__all__ = ["trace_source"]


def trace_source(source: str, stdin: str = "", max_events: int = 5000) -> Dict[str, Any]:
    """Sync wrapper around the async tracer.

    Returns a Trace Event Protocol dict. On failure (Node not on PATH,
    Inspector handshake failure, etc.) returns an error trace rather
    than raising — the route layer surfaces this to the front-end.
    """
    if not shutil.which("node"):
        return _err_result(source, stdin, "node is not installed; JS tracing requires node on PATH.")
    try:
        return asyncio.run(_trace_source_async(source, stdin, max_events))
    except InspectorError as e:
        return _err_result(source, stdin, f"inspector: {e}")
    except Exception as e:  # pragma: no cover - belt-and-suspenders
        return _err_result(source, stdin, f"tracer failed: {type(e).__name__}: {e}")


async def _trace_source_async(
    source: str, stdin: str, max_events: int
) -> Dict[str, Any]:
    work = Path(tempfile.mkdtemp(prefix="dsaviz-js-"))
    script_path = work / "user.js"
    script_path.write_text(source, encoding="utf-8")
    # Resolved absolute path V8 reports for our user code. We identify
    # user frames by matching this against callFrame.url (a file:// URI).
    user_script_url = "file://" + str(script_path.resolve())

    proc, ws_url = await spawn_node_inspector(str(script_path))
    events: List[dict] = []
    truncated = False
    addr_to_id: Dict[str, str] = {}
    heap: Dict[str, Dict[str, Any]] = {}

    try:
        async with await InspectorSession.connect(ws_url) as session:
            await session.enable_domains()
            await session.run_if_waiting_for_debugger()

            prev_depth = 0
            async for paused in session.paused_events():
                all_frames = paused.get("callFrames") or []
                # V8 reports url="" on every callFrame; resolve via the
                # scriptId → url map from Debugger.scriptParsed. A frame
                # is "user code" if its script's URL matches the temp
                # file we wrote (handling /var ↔ /private/var symlink
                # on macOS by also accepting the resolved variant).
                def is_user_frame(f: Dict[str, Any]) -> bool:
                    sid = f.get("location", {}).get("scriptId")
                    url = session.script_urls.get(sid, "") if sid else ""
                    return url == user_script_url
                call_frames = [f for f in all_frames if is_user_frame(f)]
                if not call_frames:
                    # Currently inside Node internals; step out and try
                    # again without emitting an event.
                    try:
                        await session.step_into()
                    except InspectorError:
                        break
                    continue

                depth = len(call_frames)

                # Synthesise call / return from depth diff so the trace
                # carries the `kind:"call"`/`kind:"return"` markers the
                # recursion-tree builder consumes.
                if depth > prev_depth:
                    events.append(
                        await _make_event(
                            kind="call",
                            paused=paused,
                            call_frames=call_frames,
                            session=session,
                            heap=heap,
                            addr_to_id=addr_to_id,
                            t=len(events),
                        )
                    )
                    if len(events) >= max_events:
                        truncated = True
                        break
                elif depth < prev_depth:
                    events.append(
                        await _make_event(
                            kind="return",
                            paused=paused,
                            call_frames=call_frames,
                            session=session,
                            heap=heap,
                            addr_to_id=addr_to_id,
                            t=len(events),
                        )
                    )
                    if len(events) >= max_events:
                        truncated = True
                        break

                events.append(
                    await _make_event(
                        kind="step",
                        paused=paused,
                        call_frames=call_frames,
                        session=session,
                        heap=heap,
                        addr_to_id=addr_to_id,
                        t=len(events),
                    )
                )
                prev_depth = depth
                if len(events) >= max_events:
                    truncated = True
                    break
                try:
                    await session.step_into()
                except InspectorError:
                    # Program ended between our last step and now.
                    break
    finally:
        try:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except Exception:
                proc.kill()
        except Exception:
            pass

    return {
        "version": "0.1",
        "language": "javascript",
        "source": source,
        "stdin": stdin,
        "stdout": "",
        "stderr": "",
        "exit": {"status": "ok", "message": None, "truncated": truncated},
        "events": events,
    }


NODE_WRAPPER_LOCALS = {
    "exports", "require", "module", "__filename", "__dirname",
}


async def _make_event(
    *,
    kind: str,
    paused: Dict[str, Any],
    call_frames: List[Dict[str, Any]],
    session: InspectorSession,
    heap: Dict[str, Dict[str, Any]],
    addr_to_id: Dict[str, str],
    t: int,
) -> Dict[str, Any]:
    """Build one TraceEvent dict from a Debugger.paused payload + the
    already-user-filtered `call_frames` from the orchestrator.

    Walks the topmost frame's local scope only — Node's CommonJS wrapper
    args (`exports`/`require`/`module`/`__filename`/`__dirname`) are
    excluded because they explode the heap with internal Node objects.
    """
    location = call_frames[0].get("location", {})
    line = location.get("lineNumber", 0) + 1  # V8 is 0-indexed.

    # Reverse to bottom-of-stack first.
    stack_repr: List[Dict[str, Any]] = []
    for i, frame in enumerate(reversed(call_frames)):
        is_top = i == len(call_frames) - 1
        func = frame.get("functionName") or "<anonymous>"
        file = frame.get("url") or "user.js"
        ln = frame.get("location", {}).get("lineNumber", 0) + 1
        locals_map: Dict[str, Dict[str, Any]] = {}
        if is_top:
            for scope in frame.get("scopeChain") or []:
                if scope.get("type") not in {"local", "block", "catch"}:
                    continue
                obj = scope.get("object") or {}
                object_id = obj.get("objectId")
                if not object_id:
                    continue
                try:
                    props = await session.get_properties(object_id, own_properties=True)
                except InspectorError:
                    props = []
                for p in props:
                    name = p.get("name")
                    if not name or name.startswith("__"):
                        continue
                    if name in NODE_WRAPPER_LOCALS:
                        continue
                    value_ro = p.get("value")
                    if value_ro is None:
                        continue
                    locals_map[name] = await encode_remote_object(
                        value_ro, session, addr_to_id, heap
                    )
        stack_repr.append({
            "func": func,
            "file": file,
            "line": ln,
            "locals": locals_map,
            "args": list(locals_map.keys()) if is_top else [],
        })

    return {
        "t": t,
        "kind": kind,
        "line": line,
        "file": call_frames[0].get("url") or "user.js",
        "stack": stack_repr,
        "heap": dict(heap),
        "stdout_delta": None,
        "exception": None,
    }


def _err_result(source: str, stdin: str, msg: str) -> Dict[str, Any]:
    return {
        "version": "0.1",
        "language": "javascript",
        "source": source,
        "stdin": stdin,
        "stdout": "",
        "stderr": msg,
        "exit": {"status": "error", "message": msg, "truncated": False},
        "events": [],
    }
