"""AI explainer (stretch goal).

Stub route. Wire an Anthropic / OpenAI call here once an API key is in
the environment. The response shape is fixed so the front-end can be
built against it today.

Request:
  {
    "event": { "line": int, "func": str, "locals": dict },
    "source": str
  }

Response:
  { "text": "one-line natural-language explanation" }
"""
from __future__ import annotations

import os
from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel


router = APIRouter()


class ExplainRequest(BaseModel):
    event: Dict[str, Any]
    source: str


@router.post("/explain")
def explain(req: ExplainRequest):
    if not os.environ.get("DSA_VIZ_AI_KEY"):
        raise HTTPException(
            status_code=501,
            detail=(
                "AI explainer is a stretch-goal stub. Set DSA_VIZ_AI_KEY and "
                "wire a provider (Anthropic/OpenAI) in routes/explain.py."
            ),
        )
    # Once an API key is wired, build a tight prompt around the active line
    # and locals, request a single short sentence, return the text.
    raise HTTPException(status_code=501, detail="Provider not yet implemented.")
