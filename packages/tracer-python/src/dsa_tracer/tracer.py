"""Core tracer.

Runs user source via ``exec`` with ``sys.settrace`` installed and emits a
Trace Event Protocol document.

Design notes
------------
* We compile the user source against a fixed filename ("<user>") so that we
  can filter library frames out of the trace.
* We capture stdout into an in-memory buffer so we can attach `stdout_delta`
  to each step.
* We cap the number of events with ``max_events`` so a runaway loop can't
  produce gigabytes of trace.
* "step" events fire on the *line* trace hook; we additionally synthesise
  "call" and "return" events at function boundaries so the front-end can
  animate the call stack.
"""

from __future__ import annotations

import io
import sys
import traceback
from contextlib import redirect_stdout
from dataclasses import dataclass, field
from types import FrameType
from typing import Any, Dict, List, Optional, TypedDict

from .encoder import HeapEncoder, encode_frame_locals

USER_FILENAME = "<user>"


class TraceResult(TypedDict):
    version: str
    language: str
    source: str
    stdin: str
    stdout: str
    stderr: str
    exit: dict
    events: List[dict]


@dataclass
class _TraceState:
    encoder: HeapEncoder = field(default_factory=HeapEncoder)
    events: List[dict] = field(default_factory=list)
    stdout_buf: io.StringIO = field(default_factory=io.StringIO)
    max_events: int = 5000
    truncated: bool = False
    user_filename: str = USER_FILENAME


# ---------------------------------------------------------------------- #
# public entrypoint
# ---------------------------------------------------------------------- #

def trace_source(
    source: str,
    stdin: str = "",
    max_events: int = 5000,
) -> TraceResult:
    """Compile and run ``source``, return a Trace Event Protocol doc."""
    state = _TraceState(max_events=max_events)

    # Compile once; this gives nice SyntaxError reporting separately
    # from runtime errors.
    try:
        code_obj = compile(source, USER_FILENAME, "exec")
    except SyntaxError as e:
        return _result(
            source=source,
            stdin=stdin,
            stdout="",
            stderr=f"SyntaxError: {e.msg} (line {e.lineno})",
            exit_status="error",
            events=[],
        )

    user_globals: Dict[str, Any] = {"__name__": "__main__", "__file__": USER_FILENAME}

    # Wire up stdin.
    fake_stdin = io.StringIO(stdin)
    old_stdin = sys.stdin
    sys.stdin = fake_stdin

    exit_status = "ok"
    exit_message: Optional[str] = None
    stderr_str = ""

    try:
        with redirect_stdout(state.stdout_buf):
            sys.settrace(_make_tracefn(state))
            try:
                exec(code_obj, user_globals)
            except _TraceLimitReached:
                exit_status = "timeout"
                exit_message = f"Trace exceeded max_events={max_events}"
            except SystemExit:
                # Treat as normal completion.
                pass
            except Exception as e:
                exit_status = "error"
                exit_message = f"{type(e).__name__}: {e}"
                stderr_str = traceback.format_exc()
            finally:
                sys.settrace(None)
    finally:
        sys.stdin = old_stdin

    return _result(
        source=source,
        stdin=stdin,
        stdout=state.stdout_buf.getvalue(),
        stderr=stderr_str,
        exit_status=exit_status,
        exit_message=exit_message,
        events=state.events,
        truncated=state.truncated,
    )


# ---------------------------------------------------------------------- #
# internals
# ---------------------------------------------------------------------- #

class _TraceLimitReached(BaseException):
    """Raised internally when the event cap is hit. BaseException so user
    `except Exception` blocks don't swallow it."""


def _make_tracefn(state: _TraceState):
    """Build the function passed to ``sys.settrace`` & ``frame.f_trace``."""

    def is_user_frame(frame: FrameType) -> bool:
        return frame.f_code.co_filename == state.user_filename

    def emit(kind: str, frame: FrameType, *, exception: Optional[dict] = None) -> None:
        if len(state.events) >= state.max_events:
            state.truncated = True
            raise _TraceLimitReached()

        # Build stack from bottom (outermost) to top (current).
        stack_frames: List[FrameType] = []
        f: Optional[FrameType] = frame
        while f is not None:
            if is_user_frame(f):
                stack_frames.append(f)
            f = f.f_back
        stack_frames.reverse()

        # Reset encoder each event for simplicity (v0.1 sends full heap).
        # A future version can diff heaps between events for size.
        state.encoder = HeapEncoder()

        stack_repr = []
        for sf in stack_frames:
            stack_repr.append({
                "func": sf.f_code.co_name,
                "file": sf.f_code.co_filename,
                "line": sf.f_lineno,
                "locals": encode_frame_locals(sf.f_locals, state.encoder),
                "args": list(sf.f_code.co_varnames[: sf.f_code.co_argcount]),
            })

        # Compute stdout delta since last event.
        cur_stdout = state.stdout_buf.getvalue()
        prev_total = sum(len(e.get("stdout_delta") or "") for e in state.events)
        delta = cur_stdout[prev_total:] if len(cur_stdout) > prev_total else None

        event = {
            "t": len(state.events),
            "kind": kind,
            "line": frame.f_lineno,
            "file": frame.f_code.co_filename,
            "stack": stack_repr,
            "heap": state.encoder.heap,
            "stdout_delta": delta,
            "exception": exception,
        }
        state.events.append(event)

    def local_trace(frame: FrameType, event: str, arg: Any):
        if not is_user_frame(frame):
            return None
        if event == "line":
            emit("step", frame)
        elif event == "return":
            emit("return", frame)
        elif event == "exception":
            exc_type, exc_val, _tb = arg if isinstance(arg, tuple) else (None, None, None)
            emit(
                "exception",
                frame,
                exception={
                    "type": getattr(exc_type, "__name__", "Exception"),
                    "message": str(exc_val) if exc_val is not None else "",
                },
            )
        return local_trace

    def global_trace(frame: FrameType, event: str, arg: Any):
        if not is_user_frame(frame):
            # Don't trace into stdlib; but we still need to return
            # `local_trace` so it's invoked when control re-enters user code.
            return global_trace
        if event == "call":
            emit("call", frame)
            return local_trace
        return local_trace

    return global_trace


def _result(
    *,
    source: str,
    stdin: str,
    stdout: str,
    stderr: str,
    exit_status: str,
    exit_message: Optional[str] = None,
    events: Optional[List[dict]] = None,
    truncated: bool = False,
) -> TraceResult:
    res: TraceResult = {
        "version": "0.1",
        "language": "python",
        "source": source,
        "stdin": stdin,
        "stdout": stdout,
        "stderr": stderr,
        "exit": {"status": exit_status, "message": exit_message, "truncated": truncated},
        "events": events or [],
    }
    return res
