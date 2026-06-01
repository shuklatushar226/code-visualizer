"""POST /trace — turn user code into a Trace Event Protocol document."""

from __future__ import annotations

import shutil

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..config import config
from ..sandbox import (
    run_cpp_in_sandbox,
    run_java_in_sandbox,
    run_js_in_sandbox,
    run_python_in_sandbox,
)

router = APIRouter()


class TraceRequest(BaseModel):
    language: str = Field(..., description="One of: python, cpp, javascript, java")
    source: str = Field(..., max_length=200_000)
    stdin: str = Field(default="", max_length=64_000)


@router.post("/trace")
def trace(req: TraceRequest):
    # Reject oversize sources with a clean 413 rather than letting the sandbox
    # raise a bare ValueError (which would surface as a generic 500).
    if len(req.source.encode("utf-8")) > config.max_source_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"source exceeds the maximum of {config.max_source_bytes} bytes",
        )
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
