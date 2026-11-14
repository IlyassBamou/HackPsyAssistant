"""Coordinates one patient message: scoring -> trajectory -> (alerts) -> LLM -> storage.

Contains no model itself; it only chains the services. All state lives in the patient's
JSON files (storage_service), so trends cover every conversation of the patient.
"""
from __future__ import annotations

from ..core.config import AXES
from . import llm_service, storage_service as storage
from .scorer import load_scorer
from .trajectory import analyze

scorer = load_scorer()


class PatientNotFound(KeyError):
    pass


def get_patient(pid: str) -> dict:
    patient = storage.get_patient(pid)
    if patient is None:
        raise PatientNotFound(pid)
    return patient


def active_axes(patient: dict) -> list[str]:
    return [a for a in patient.get("active_axes", AXES) if a in AXES]


def patient_state(pid: str, patient: dict | None = None) -> dict:
    patient = patient or get_patient(pid)
    active = active_axes(patient)
    analyses = storage.get_analyses(pid)
    return {"patient_id": pid, "scorer": scorer.name, "axes": {a: AXES[a] for a in active},
            "analysis": analyze([a["scores"] for a in analyses], active),
            "explanations": [a["explanation"] for a in analyses[-10:]]}


def patient_overview(pid: str) -> dict:
    patient = get_patient(pid)
    recent = [{"role": m["role"], "content": m["content"], "conversation_id": m["conversation_id"], "ts": m["ts"]}
              for m in storage.get_messages(pid)[-20:]]
    return {**patient_state(pid, patient), "patient": patient, "recent_messages": recent}


def update_settings(pid: str, doctor_context: str | None = None, axes: list[str] | None = None) -> dict:
    get_patient(pid)
    fields = {}
    if doctor_context is not None:
        fields["doctor_context"] = doctor_context
    if axes is not None:
        fields["active_axes"] = [a for a in axes if a in AXES]
    patient = storage.update_patient(pid, **fields) if fields else None
    return patient_state(pid, patient)


def score_message(message: str) -> dict:
    return {"scores": scorer.score(message), "explanation": scorer.explain(message)}


def process_patient_message(pid: str, message: str, conversation_id: str | None = None) -> dict:
    patient = get_patient(pid)
    conv = conversation_id or storage.new_id()
    # 1. save and analyse the message on the 5 axes
    msg = storage.add_message(pid, conv, "user", message)
    storage.add_analysis(pid, {"message_id": msg["id"], "conversation_id": conv, "ts": msg["ts"],
                               "scorer": scorer.name, **score_message(message)})
    # 2. update temporal trends over the whole patient history (alerts come from here until alert_service)
    state = patient_state(pid, patient)
    analysis = state["analysis"]
    storage.add_mood_entry(pid, {"ts": msg["ts"], "message_id": msg["id"], "conversation_id": conv,
                                 "index": analysis["index"], "levels": analysis["levels"]})
    # 3. personalised reply from the current conversation
    convo = [{"role": m["role"], "content": m["content"]} for m in storage.get_messages(pid, conv)]
    reply, src = llm_service.chat_reply(patient.get("doctor_context", ""), convo, analysis)
    storage.add_message(pid, conv, "assistant", reply, source=src)
    return {**state, "conversation_id": conv, "reply": reply, "reply_source": src}


def summarize_conversation(pid: str, conversation_id: str | None = None) -> dict:
    patient = get_patient(pid)
    convo = [{"role": m["role"], "content": m["content"]} for m in storage.get_messages(pid, conversation_id)]
    analysis = patient_state(pid, patient)["analysis"]
    text, src = llm_service.summarize(patient.get("doctor_context", ""), convo, analysis)
    storage.add_report(pid, {"type": "ai_session_summary", "conversation_id": conversation_id,
                             "source": src, "summary": text})
    return {"summary": text, "source": src}
