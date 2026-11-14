"""Patient profiles, psychiatrist settings, and the demo journey."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from ..services import conversation_orchestrator as orchestrator
from ..services import storage_service as storage

router = APIRouter(prefix="/api", tags=["patients"])
DATA = Path(__file__).resolve().parent.parent / "data"


class SettingsIn(BaseModel):
    doctor_context: str | None = None
    axes: list[str] | None = None


@router.get("/patients")
def list_patients():
    return storage.list_patients()


@router.get("/patients/{patient_id}")
def get_patient(patient_id: str):
    return orchestrator.patient_overview(patient_id)


@router.patch("/patients/{patient_id}")
def update_settings(patient_id: str, body: SettingsIn):
    return orchestrator.update_settings(patient_id, body.doctor_context, body.axes)


@router.delete("/patients/{patient_id}/history")
def clear_history(patient_id: str):
    """Erase generated data (conversations, scores, alerts, summaries); profile and reports are kept."""
    orchestrator.get_patient(patient_id)
    storage.clear_history(patient_id)
    return orchestrator.patient_state(patient_id)


@router.get("/demo")
def demo():
    return json.loads((DATA / "demo_journey.json").read_text())
