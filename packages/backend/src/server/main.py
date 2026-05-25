"""FastAPI entrypoint.

Run locally with:
    uvicorn server.main:app --reload --port 8000
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import config
from .routes import health, trace

app = FastAPI(
    title="DSA Code Visualizer Backend",
    version="0.1.0",
    description="Turn student code into Trace Event Protocol JSON, sandboxed.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(config.allowed_origins) or ["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(trace.router)
