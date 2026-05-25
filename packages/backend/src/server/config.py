"""Server configuration (env-driven)."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    sandbox_timeout_seconds: int = int(os.environ.get("SANDBOX_TIMEOUT_SECONDS", "5"))
    max_trace_events: int = int(os.environ.get("MAX_TRACE_EVENTS", "5000"))
    allowed_origins: tuple[str, ...] = tuple(
        o.strip()
        for o in os.environ.get(
            "ALLOWED_ORIGINS",
            "http://localhost:5173,chrome-extension://*",
        ).split(",")
        if o.strip()
    )
    # Hard limit on the size of a submission to guard against DoS.
    max_source_bytes: int = int(os.environ.get("MAX_SOURCE_BYTES", "65536"))


config = Config()
