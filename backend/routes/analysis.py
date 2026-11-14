"""Scoring results and analysis configuration."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ..core.config import AXES
from ..services import conversation_orchestrator as orchestrator
from ..services import llm_service

router = APIRouter(prefix="/api", tags=["analysis"])


class ScoreIn(BaseModel):
    message: str


@router.get("/config")
def config():
    return {"axes": AXES, "scorer": orchestrator.scorer.name, "llm": llm_service.MODEL}


@router.post("/score")
def score_only(body: ScoreIn):
    return orchestrator.score_message(body.message)
