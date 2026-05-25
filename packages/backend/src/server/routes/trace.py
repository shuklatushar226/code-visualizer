"""POST /trace — turn user code into a Trace Event Protocol document."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..config import config
from ..sandbox import run_python_in_sandbox

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
        raise HTTPException(
            status_code=501,
            detail="C++ tracing is part of milestone M3 — see docs/ROADMAP.md.",
        )
    raise HTTPException(status_code=400, detail=f"Unsupported language: {req.language}")
