"""Liveness / readiness endpoints."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/healthz")
def healthz():
    return {"status": "ok"}


@router.get("/version")
def version():
    return {"version": "0.1.0", "protocol": "0.1"}
