"""Liveness, version, and runtime-capability endpoints."""

import os
import shutil

from fastapi import APIRouter

router = APIRouter()


@router.get("/healthz")
def healthz():
    return {"status": "ok"}


@router.get("/version")
def version():
    return {"version": "0.1.0", "protocol": "0.1"}


@router.get("/capabilities")
def capabilities():
    """Report what this concrete deployment can execute.

    Tracer packages may be installed while their external toolchain is not
    (Java on the slim hosted image is the common example). The web app uses
    this response instead of advertising source-level support as live support.
    """

    runtimes = {
        "python": {"available": True, "reason": None},
        "cpp": {
            "available": bool(shutil.which("gdb") and shutil.which("g++")),
            "reason": None,
        },
        "javascript": {
            "available": bool(shutil.which("node")),
            "reason": None,
        },
        "java": {
            "available": bool(shutil.which("javac") and shutil.which("java")),
            "reason": None,
        },
    }
    requirements = {
        "cpp": "requires gdb and g++",
        "javascript": "requires Node.js 18+",
        "java": "local tracer available; hosted runtime requires JDK 17+",
    }
    for language, requirement in requirements.items():
        if not runtimes[language]["available"]:
            runtimes[language]["reason"] = requirement

    provider = (os.environ.get("DSA_VIZ_AI_PROVIDER") or "anthropic").lower()
    ai_available = provider == "fixture" or bool(os.environ.get("DSA_VIZ_AI_KEY"))
    return {
        "runtimes": runtimes,
        "ai_explain": {
            "available": ai_available,
            "reason": None if ai_available else "AI explanation is not configured on this deployment",
        },
        "isolation": "container" if os.environ.get("USE_DOCKER_SANDBOX") == "1" else "process",
    }
