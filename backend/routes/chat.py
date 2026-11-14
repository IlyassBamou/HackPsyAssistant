"""Patient messages."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ..services import conversation_orchestrator as orchestrator

router = APIRouter(prefix="/api", tags=["chat"])


class ChatIn(BaseModel):
    patient_id: str
    message: str
    conversation_id: str | None = None


@router.post("/chat")
def chat(body: ChatIn):
    return orchestrator.process_patient_message(body.patient_id, body.message, body.conversation_id)
