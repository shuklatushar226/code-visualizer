"""AI explainer — POST /explain.

Streams a one-sentence natural-language explanation of the line that is
executing at the current trace event. The route plumbs together:

  - Prompt construction from the trace event + source
  - LRU cache by (sha256(source), line, language)
  - Per-IP token-bucket rate limit (30 req/min)
  - Streaming via Server-Sent Events (text/event-stream)
  - Provider abstraction (AnthropicProvider in prod, FixtureProvider in tests)

Without `DSA_VIZ_AI_KEY` and with provider defaulting to "anthropic",
provider init raises AIProviderError → route returns 501 (same as the
old stub).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from collections import OrderedDict
from typing import Any, AsyncIterator, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..ai import AIProvider, AIProviderError, make_provider


router = APIRouter()


# ────────────────────────────────────────────────────────────────────
# Request model
# ────────────────────────────────────────────────────────────────────

class ExplainEvent(BaseModel):
    line: int = Field(..., ge=0)
    func: Optional[str] = None
    locals: Dict[str, Any] = Field(default_factory=dict)


class ExplainRequest(BaseModel):
    event: ExplainEvent
    source: str = Field(..., max_length=200_000)
    language: str = Field(default="python")


# ────────────────────────────────────────────────────────────────────
# Prompt construction
# ────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = (
    "You explain one line of Python or C++ code for a CS student "
    "preparing for placement interviews. Reply in ONE short sentence. "
    "No preamble. No 'this line'. Plain language. When useful, "
    "reference variable values to make the explanation concrete."
)


def build_user_prompt(req: ExplainRequest) -> str:
    lines = req.source.splitlines()
    active_line = lines[req.event.line - 1] if 0 < req.event.line <= len(lines) else ""
    locals_summary = _summarize_locals(req.event.locals)
    return (
        f"Code (language: {req.language}):\n"
        f"{req.source[:4000]}\n\n"
        f"Currently executing line {req.event.line}:\n"
        f"    {active_line.strip()}\n\n"
        f"Locals at this moment: {locals_summary}"
    )


def _summarize_locals(locals_: Dict[str, Any]) -> str:
    """Compact representation of up to 6 locals. Truncates long values."""
    items = list(locals_.items())[:6]
    pairs: List[str] = []
    for name, value in items:
        rendered = _render_value(value)
        if len(rendered) > 40:
            rendered = rendered[:37] + "..."
        pairs.append(f"{name}={rendered}")
    if not pairs:
        return "(none)"
    return ", ".join(pairs)


def _render_value(v: Any) -> str:
    if not isinstance(v, dict):
        return str(v)
    kind = v.get("kind")
    if kind in ("int", "float", "bool", "str"):
        return repr(v.get("v"))
    if kind == "none":
        return "None"
    if kind == "ref":
        return f"<{v.get('id')}>"
    return json.dumps(v, separators=(",", ":"))


# ────────────────────────────────────────────────────────────────────
# LRU cache + rate limit (in-memory; bounded; process-local)
# ────────────────────────────────────────────────────────────────────

_CACHE_MAX = 1000
_CACHE: "OrderedDict[str, str]" = OrderedDict()


def _cache_key(req: ExplainRequest) -> str:
    h = hashlib.sha256(req.source.encode("utf-8")).hexdigest()[:16]
    return f"{h}:{req.language}:{req.event.line}"


def _cache_get(key: str) -> Optional[str]:
    if key in _CACHE:
        _CACHE.move_to_end(key)
        return _CACHE[key]
    return None


def _cache_put(key: str, value: str) -> None:
    _CACHE[key] = value
    _CACHE.move_to_end(key)
    while len(_CACHE) > _CACHE_MAX:
        _CACHE.popitem(last=False)


# Token-bucket rate limiting per remote IP. State: dict[ip] = (tokens, last_refill).
_RATE_PER_MIN = int(os.environ.get("EXPLAIN_RATE_PER_MIN", "30"))
_BUCKET_CAP = _RATE_PER_MIN
_REFILL_INTERVAL = 60.0 / max(_RATE_PER_MIN, 1)
_BUCKETS: Dict[str, tuple] = {}


def _allow(ip: str) -> bool:
    now = time.monotonic()
    tokens, last = _BUCKETS.get(ip, (_BUCKET_CAP, now))
    # Refill linearly since last request.
    elapsed = now - last
    tokens = min(_BUCKET_CAP, tokens + elapsed / _REFILL_INTERVAL)
    if tokens >= 1:
        _BUCKETS[ip] = (tokens - 1, now)
        return True
    _BUCKETS[ip] = (tokens, now)
    return False


# ────────────────────────────────────────────────────────────────────
# Route
# ────────────────────────────────────────────────────────────────────

# Lazy provider — initialized on first request so test fixtures can
# monkeypatch `make_provider` before the route runs.
_PROVIDER: Optional[AIProvider] = None


def _get_provider() -> AIProvider:
    global _PROVIDER
    if _PROVIDER is None:
        _PROVIDER = make_provider()
    return _PROVIDER


def _reset_provider() -> None:
    """Test helper: clear the lazy provider so tests can re-init it."""
    global _PROVIDER
    _PROVIDER = None


@router.post("/explain")
async def explain(req: ExplainRequest, request: Request) -> StreamingResponse:
    ip = request.client.host if request.client else "unknown"
    if not _allow(ip):
        raise HTTPException(status_code=429, detail="rate limit exceeded")

    key = _cache_key(req)
    cached = _cache_get(key)
    if cached is not None:
        return StreamingResponse(_one_shot_sse(cached), media_type="text/event-stream")

    try:
        provider = _get_provider()
    except AIProviderError as e:
        raise HTTPException(status_code=501, detail=str(e))

    user_prompt = build_user_prompt(req)
    return StreamingResponse(
        _stream_sse(provider, user_prompt, key),
        media_type="text/event-stream",
    )


# ────────────────────────────────────────────────────────────────────
# SSE producers
# ────────────────────────────────────────────────────────────────────

async def _stream_sse(
    provider: AIProvider, user_prompt: str, cache_key: str
) -> AsyncIterator[bytes]:
    """Stream provider tokens via SSE; tee into the cache on completion."""
    parts: List[str] = []
    try:
        async for chunk in provider.stream_explain(SYSTEM_PROMPT, user_prompt):
            parts.append(chunk)
            yield _sse_event("token", chunk)
    except AIProviderError as e:
        yield _sse_event("error", str(e))
        return
    full = "".join(parts).strip()
    if full:
        _cache_put(cache_key, full)
    yield _sse_event("done", full)


async def _one_shot_sse(text: str) -> AsyncIterator[bytes]:
    yield _sse_event("token", text)
    yield _sse_event("done", text)


def _sse_event(event: str, data: str) -> bytes:
    # `data:` lines must not contain literal newlines; replace.
    safe = data.replace("\n", "\\n")
    return f"event: {event}\ndata: {safe}\n\n".encode("utf-8")
