"""Shareable trace links.

Process-local **in-memory** store keyed by a short 8-char hash. Links
survive only as long as the backend process. Suitable for single-
instance demos; for hosted deployments swap _STORE for a real KV
backend (S3+DynamoDB, Redis with persistence, etc.). The wire format
is unchanged — only the storage class needs to be swapped.
"""

from __future__ import annotations

import hashlib
import json
import threading
from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

# Process-local store. Bounded so a misbehaving caller can't OOM the host.
_MAX_ENTRIES = 1000
_MAX_TRACE_BYTES = 1_000_000
_STORE: Dict[str, Dict[str, Any]] = {}
_ORDER: list[str] = []  # insertion order for LRU-style eviction
_STORE_LOCK = threading.RLock()


class SavePayload(BaseModel):
    trace: Dict[str, Any]


def _make_code(trace: Dict[str, Any]) -> str:
    base = hashlib.sha256(json.dumps(trace, sort_keys=True).encode()).hexdigest()[:8]
    digest = base
    suffix = 0
    # Resolve collisions. A previous version re-sliced `(digest + token)[:8]`,
    # which is a no-op once `digest` is already 8 chars — so a repeat or any
    # 8-hex-prefix collision looped forever. Re-hash with an incrementing
    # suffix so each attempt yields a genuinely different 8-char code, and
    # reuse the existing code when the *identical* trace is saved again.
    while digest in _STORE:
        if _STORE[digest] == trace:
            return digest
        suffix += 1
        digest = hashlib.sha256(f"{base}:{suffix}".encode()).hexdigest()[:8]
    return digest


@router.post("/share")
def save_trace(payload: SavePayload):
    """Persist a trace and return its short code."""
    encoded = json.dumps(payload.trace, sort_keys=True, separators=(",", ":")).encode()
    if len(encoded) > _MAX_TRACE_BYTES:
        raise HTTPException(status_code=413, detail="trace is too large to share")

    with _STORE_LOCK:
        code = _make_code(payload.trace)
        already_stored = code in _STORE
        _STORE[code] = payload.trace
        if already_stored:
            # Refresh the existing entry instead of adding duplicate order
            # records that eventually evict the only stored copy.
            try:
                _ORDER.remove(code)
            except ValueError:
                pass
        _ORDER.append(code)
        while len(_ORDER) > _MAX_ENTRIES:
            evict = _ORDER.pop(0)
            _STORE.pop(evict, None)
    return {"code": code, "url": f"/t/{code}"}


@router.get("/t/{code}")
def fetch_trace(code: str):
    with _STORE_LOCK:
        trace = _STORE.get(code)
    if trace is None:
        raise HTTPException(status_code=404, detail=f"No trace with code {code!r}")
    return trace
