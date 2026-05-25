"""POST /trace — turn user code into a Trace Event Protocol document."""

from __future__ import annotations

import shutil

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..config import config
from ..sandbox import run_cpp_in_sandbox, run_python_in_sandbox

router = APIRouter()


class TraceRequest(BaseModel):
    language: str = Field(..., description="One of: python, cpp")
    source: str = Field(..., max_length=200_000)
    stdin: str = Field(default="", max_length=64_000)


@router.post("/trace")
def trace(req: TraceRequest):
    if req.language == "python":
        return run_python_in_sandbox(req.source)
    if req.language == "cpp":
        if not shutil.which("gdb") or not shutil.which("g++"):
            raise HTTPException(
                status_code=501,
                detail=(
                    "C++ tracing (M3) requires gdb and g++ on PATH. "
                    "This is typically only available on Linux; see docs/ROADMAP.md."
                ),
            )
        return run_cpp_in_sandbox(req.source)
    if req.language in {"java", "javascript", "js"}:
        raise HTTPException(
            status_code=501,
            detail=(
                f"{req.language} tracing is a stretch goal — "
                "packages/tracer-{java,js} contain skeletons; see docs/ROADMAP.md."
            ),
        )
    raise HTTPException(status_code=400, detail=f"Unsupported language: {req.language}")
