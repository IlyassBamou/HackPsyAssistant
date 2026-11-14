"""Alert consultation for the psychiatrist. Filled in with alert_service."""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["alerts"])
