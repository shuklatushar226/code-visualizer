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
import secrets
from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

# Process-local store. Bounded so a misbehaving caller can't OOM the host.
_MAX_ENTRIES = 1000
_STORE: Dict[str, Dict[str, Any]] = {}
_ORDER: list[str] = []  # insertion order for LRU-style eviction


class SavePayload(BaseModel):
    trace: Dict[str, Any]


def _make_code(trace: Dict[str, Any]) -> str:
    digest = hashlib.sha256(json.dumps(trace, sort_keys=True).encode()).hexdigest()[:8]
    # Salt with a random byte if there's already a collision so two
    # different traces can't clobber each other.
    while digest in _STORE:
        digest = (digest + secrets.token_hex(1))[:8]
    return digest


@router.post("/share")
def save_trace(payload: SavePayload):
    """Persist a trace and return its short code."""
    code = _make_code(payload.trace)
    _STORE[code] = payload.trace
    _ORDER.append(code)
    while len(_ORDER) > _MAX_ENTRIES:
        evict = _ORDER.pop(0)
        _STORE.pop(evict, None)
    return {"code": code, "url": f"/t/{code}"}


@router.get("/t/{code}")
def fetch_trace(code: str):
    trace = _STORE.get(code)
    if trace is None:
        raise HTTPException(status_code=404, detail=f"No trace with code {code!r}")
    return trace
