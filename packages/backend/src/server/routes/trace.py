"""POST /trace — turn user code into a Trace Event Protocol document."""

from __future__ import annotations

import shutil
import threading
import time
from collections import deque

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..config import config
from ..sandbox import (
    run_cpp_in_sandbox,
    run_java_in_sandbox,
    run_js_in_sandbox,
    run_python_in_sandbox,
)

router = APIRouter()

_TRACE_SLOTS = threading.BoundedSemaphore(max(1, config.max_concurrent_traces))
_TRACE_RATE_LOCK = threading.Lock()
_TRACE_REQUESTS: dict[str, deque[float]] = {}
_TRACE_CLIENTS_MAX = 10_000


def _allow_trace(ip: str) -> bool:
    """Fixed-window per-client limiter for expensive execution requests."""
    limit = config.trace_rate_per_minute
    if limit <= 0:
        return True
    now = time.monotonic()
    cutoff = now - 60.0
    with _TRACE_RATE_LOCK:
        history = _TRACE_REQUESTS.setdefault(ip, deque())
        while history and history[0] <= cutoff:
            history.popleft()
        if len(history) >= limit:
            return False
        history.append(now)

        if len(_TRACE_REQUESTS) > _TRACE_CLIENTS_MAX:
            stale = [
                client
                for client, requests in _TRACE_REQUESTS.items()
                if not requests or requests[-1] <= cutoff
            ]
            for client in stale:
                _TRACE_REQUESTS.pop(client, None)
        return True


class TraceRequest(BaseModel):
    language: str = Field(..., description="One of: python, cpp, javascript, java")
    source: str = Field(..., max_length=200_000)
    stdin: str = Field(default="", max_length=64_000)


@router.post("/trace")
def trace(req: TraceRequest, request: Request):
    # Reject oversize sources with a clean 413 rather than letting the sandbox
    # raise a bare ValueError (which would surface as a generic 500).
    if len(req.source.encode("utf-8")) > config.max_source_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"source exceeds the maximum of {config.max_source_bytes} bytes",
        )
    if not _TRACE_SLOTS.acquire(blocking=False):
        raise HTTPException(
            status_code=503,
            detail="trace capacity is busy; retry shortly",
            headers={"Retry-After": "1"},
        )
    try:
        ip = request.client.host if request.client else "unknown"
        if not _allow_trace(ip):
            raise HTTPException(
                status_code=429,
                detail="trace rate limit exceeded",
                headers={"Retry-After": "60"},
            )
        return _dispatch_trace(req)
    finally:
        _TRACE_SLOTS.release()


def _dispatch_trace(req: TraceRequest):
    if req.language == "python":
        return run_python_in_sandbox(req.source, req.stdin)
    if req.language == "cpp":
        if not shutil.which("gdb") or not shutil.which("g++"):
            raise HTTPException(
                status_code=501,
                detail=(
                    "C++ tracing (M3) requires gdb and g++ on PATH. "
                    "This is typically only available on Linux; see docs/ROADMAP.md."
                ),
            )
        return run_cpp_in_sandbox(req.source, req.stdin)
    if req.language in {"javascript", "js"}:
        if not shutil.which("node"):
            raise HTTPException(
                status_code=501,
                detail=(
                    "JavaScript tracing requires node on PATH. "
                    "Install Node.js ≥18 to enable; see docs/ROADMAP.md."
                ),
            )
        return run_js_in_sandbox(req.source, req.stdin)
    if req.language == "java":
        if not shutil.which("javac") or not shutil.which("java"):
            raise HTTPException(
                status_code=501,
                detail=(
                    "Java tracing requires a JDK (javac and java) on PATH. "
                    "Install a JDK 17+ to enable; see docs/ROADMAP.md."
                ),
            )
        return run_java_in_sandbox(req.source, req.stdin)
    raise HTTPException(status_code=400, detail=f"Unsupported language: {req.language}")
