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

    # Production-grade container sandbox. When enabled, each /trace request
    # spawns `docker run` instead of a same-process subprocess. The image is
    # built from packages/backend/Dockerfile.sandbox.
    use_docker_sandbox: bool = os.environ.get("USE_DOCKER_SANDBOX", "0") == "1"
    docker_sandbox_image: str = os.environ.get("DOCKER_SANDBOX_IMAGE", "dsa-viz-sandbox")
    docker_seccomp_profile: str = os.environ.get(
        "DOCKER_SECCOMP_PROFILE",
        # Default to the bundled profile; an absolute path overrides.
        str(os.path.join(os.path.dirname(__file__), "..", "..", "sandbox.seccomp.json")),
    )


config = Config()
