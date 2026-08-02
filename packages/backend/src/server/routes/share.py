"""Durable shareable trace links backed by SQLite.

The database path is configured with ``SHARE_DB_PATH``. SQLite is deliberately
used here because the demo is single-service and needs no extra dependency; a
mounted volume makes links survive restarts and deploys. The HTTP contract is
unchanged if the storage layer is replaced with managed Redis/Postgres later.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config import config

router = APIRouter()

_MAX_ENTRIES = 1000
_MAX_TRACE_BYTES = 1_000_000
_DB_LOCK = threading.RLock()
_CONNECTION: sqlite3.Connection | None = None
_CONNECTION_PATH: str | None = None


class SavePayload(BaseModel):
    trace: Dict[str, Any]


def _connection() -> sqlite3.Connection:
    global _CONNECTION, _CONNECTION_PATH
    path = config.share_db_path
    with _DB_LOCK:
        if _CONNECTION is not None and _CONNECTION_PATH == path:
            return _CONNECTION
        if _CONNECTION is not None:
            _CONNECTION.close()
        if path != ":memory:":
            Path(path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        _CONNECTION = sqlite3.connect(path, check_same_thread=False)
        _CONNECTION.row_factory = sqlite3.Row
        _CONNECTION.execute(
            """
            CREATE TABLE IF NOT EXISTS shared_traces (
                code TEXT PRIMARY KEY,
                trace_json TEXT NOT NULL,
                byte_size INTEGER NOT NULL,
                updated_at REAL NOT NULL
            )
            """
        )
        _CONNECTION.commit()
        _CONNECTION_PATH = path
        return _CONNECTION


def _make_code(encoded: str, db: sqlite3.Connection) -> str:
    base = hashlib.sha256(encoded.encode()).hexdigest()[:8]
    suffix = 0
    while True:
        code = (
            base
            if suffix == 0
            else hashlib.sha256(f"{base}:{suffix}".encode()).hexdigest()[:8]
        )
        existing = db.execute(
            "SELECT trace_json FROM shared_traces WHERE code = ?", (code,)
        ).fetchone()
        if existing is None or existing["trace_json"] == encoded:
            return code
        suffix += 1


@router.post("/share")
def save_trace(payload: SavePayload):
    """Persist a trace and return its stable short code."""

    encoded = json.dumps(payload.trace, sort_keys=True, separators=(",", ":"))
    byte_size = len(encoded.encode())
    if byte_size > _MAX_TRACE_BYTES:
        raise HTTPException(status_code=413, detail="trace is too large to share")

    with _DB_LOCK:
        db = _connection()
        code = _make_code(encoded, db)
        db.execute(
            """
            INSERT INTO shared_traces(code, trace_json, byte_size, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(code) DO UPDATE SET updated_at = excluded.updated_at
            """,
            (code, encoded, byte_size, time.time()),
        )
        overflow = db.execute(
            "SELECT MAX(COUNT(*) - ?, 0) FROM shared_traces", (_MAX_ENTRIES,)
        ).fetchone()[0]
        if overflow:
            db.execute(
                """
                DELETE FROM shared_traces WHERE code IN (
                    SELECT code FROM shared_traces ORDER BY updated_at ASC LIMIT ?
                )
                """,
                (overflow,),
            )
        db.commit()
    return {"code": code, "url": f"/t/{code}"}


@router.get("/t/{code}")
def fetch_trace(code: str):
    with _DB_LOCK:
        row = _connection().execute(
            "SELECT trace_json FROM shared_traces WHERE code = ?", (code,)
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"No trace with code {code!r}")
    return json.loads(row["trace_json"])


def _reset_connection_for_tests(path: str) -> None:
    """Point the module at an isolated database. Test-only helper."""

    global _CONNECTION, _CONNECTION_PATH
    with _DB_LOCK:
        if _CONNECTION is not None:
            _CONNECTION.close()
        _CONNECTION = None
        _CONNECTION_PATH = None
        object.__setattr__(config, "share_db_path", path)
