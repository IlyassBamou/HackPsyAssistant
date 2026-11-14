"""Consultation reports and session summaries for the psychiatrist."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ..services import conversation_orchestrator as orchestrator
from ..services import storage_service as storage

router = APIRouter(prefix="/api", tags=["reports"])


class SummaryIn(BaseModel):
    patient_id: str
    conversation_id: str | None = None


@router.get("/reports/{patient_id}")
def list_reports(patient_id: str):
    orchestrator.get_patient(patient_id)
    return storage.get_reports(patient_id)


@router.post("/summary")
def summary(body: SummaryIn):
    return orchestrator.summarize_conversation(body.patient_id, body.conversation_id)
