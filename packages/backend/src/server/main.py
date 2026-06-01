"""FastAPI entrypoint.

Run locally with:
    uvicorn server.main:app --reload --port 8000
"""

import os
import re

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import config
from .routes import explain, health, share, trace

app = FastAPI(
    title="DSA Code Visualizer Backend",
    version="0.1.0",
    description="Turn student code into Trace Event Protocol JSON, sandboxed.",
)

# Starlette's `allow_origins` does EXACT string matching (only the literal "*"
# is special). A glob like "chrome-extension://*" therefore never matches a real
# extension origin such as "chrome-extension://abcdef...". Translate any
# "scheme://*" entries into an `allow_origin_regex` so the browser extension —
# whose origin is unpredictable — is actually permitted.
_exact_origins = [o for o in config.allowed_origins if not o.endswith("://*")]
_glob_origins = [o for o in config.allowed_origins if o.endswith("://*")]
_origin_regex = (
    "|".join(re.escape(o[: -len("*")]) + ".*" for o in _glob_origins)
    if _glob_origins
    else None
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_exact_origins or (["*"] if not _origin_regex else []),
    allow_origin_regex=_origin_regex,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(trace.router)
app.include_router(share.router)
app.include_router(explain.router)

# Serve the built single-page app when present (combined-service deploy). The
# Docker image copies the Vite `dist/` into STATIC_DIR; mounting it LAST means the
# explicit API routes above always take precedence, while `html=True` makes the
# mount return index.html for any other path (SPA entrypoint). When the directory
# is absent (e.g. local API-only dev), this is simply skipped.
_static_dir = os.environ.get("STATIC_DIR", "/app/static")
if os.path.isdir(_static_dir):
    app.mount("/", StaticFiles(directory=_static_dir, html=True), name="spa")
