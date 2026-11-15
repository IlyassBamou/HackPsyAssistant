"""FastAPI app: patient chat (text + audio), doctor dashboard, alerts, and the JSON API."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import llm
from .config import AXES
from .scorer import load_scorer
from .trajectory import analyze

HERE = Path(__file__).parent
app = FastAPI(title="HackPsyAssistant")
scorer = load_scorer()
SESSIONS: dict[str, dict] = {}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _session(sid: str | None, context: str | None = None, active: list[str] | None = None,
             name: str | None = None) -> tuple[str, dict]:
    sid = sid or uuid.uuid4().hex[:8]
    s = SESSIONS.setdefault(sid, {
        "name": name or "Patient anonyme", "context": "", "active": list(AXES),
        "convo": [], "scores": [], "expl": [], "alert_log": [],
        "created": _now(), "updated": _now(),
    })
    if context is not None:
        s["context"] = context
    if active:
        s["active"] = [a for a in active if a in AXES]
    if name:
        s["name"] = name
    return sid, s


class ChatIn(BaseModel):
    session_id: str | None = None
    message: str
    context: str | None = None
    axes: list[str] | None = None
    patient_name: str | None = None


class SessionIn(BaseModel):
    session_id: str | None = None
    context: str | None = None
    axes: list[str] | None = None
    patient_name: str | None = None


def _state(sid: str, s: dict) -> dict:
    return {"session_id": sid, "scorer": scorer.name, "axes": {a: AXES[a] for a in s["active"]},
            "analysis": analyze(s["scores"], s["active"]), "explanations": s["expl"]}


def _log_new_alerts(s: dict, analysis: dict, message: str) -> list[dict]:
    """Compare current alerts with the previously active set; log and return the new ones."""
    prev = s.get("_active_alerts", set())
    cur = {a["axis"] for a in analysis["alerts"]}
    new = []
    for a in analysis["alerts"]:
        if a["axis"] not in prev:
            entry = {**a, "ts": _now(), "msg_index": len(s["scores"]), "message": message, "seen": False}
            s["alert_log"].append(entry)
            new.append(entry)
    s["_active_alerts"] = cur
    return new


# ---------------------------------------------------------------- patient API

@app.get("/api/config")
def config():
    return {"axes": AXES, "scorer": scorer.name, "llm": llm.MODEL}


@app.post("/api/session")
def session(body: SessionIn):
    sid, s = _session(body.session_id, body.context, body.axes, body.patient_name)
    s["updated"] = _now()
    return _state(sid, s)


@app.post("/api/chat")
def chat(body: ChatIn):
    sid, s = _session(body.session_id, body.context, body.axes, body.patient_name)
    s["convo"].append({"role": "user", "content": body.message, "ts": _now()})
    s["scores"].append(scorer.score(body.message))
    s["expl"].append(scorer.explain(body.message))
    analysis = analyze(s["scores"], s["active"])
    new_alerts = _log_new_alerts(s, analysis, body.message)
    reply, src = llm.chat_reply(s["context"], [{"role": m["role"], "content": m["content"]} for m in s["convo"]], analysis)
    s["convo"].append({"role": "assistant", "content": reply, "ts": _now()})
    s["updated"] = _now()
    return {**_state(sid, s), "reply": reply, "reply_source": src,
            "new_alerts": [{"label": a["label"], "recommendation": a["recommendation"],
                            "critical": a["critical"]} for a in new_alerts]}


@app.post("/api/transcribe")
async def transcribe(request: Request):
    import anyio.to_thread

    from . import stt
    body = await request.body()
    if len(body) < 100:
        raise HTTPException(400, "audio vide")
    try:
        text = await anyio.to_thread.run_sync(stt.transcribe, body)
    except Exception as e:
        raise HTTPException(500, f"transcription impossible: {e}")
    return {"text": text}


@app.get("/api/stt/warmup")
def stt_warmup():
    from . import stt
    return {"model": stt.warmup()}


@app.post("/api/summary")
def summary(body: SessionIn):
    if not body.session_id or body.session_id not in SESSIONS:
        raise HTTPException(404, "unknown session")
    s = SESSIONS[body.session_id]
    convo = [{"role": m["role"], "content": m["content"]} for m in s["convo"]]
    text, src = llm.summarize(s["context"], convo, analyze(s["scores"], s["active"]))
    return {"summary": text, "source": src}


@app.get("/api/demo")
def demo():
    return json.loads((HERE / "demo_journey.json").read_text())


# ---------------------------------------------------------------- doctor API

@app.get("/api/doctor/patients")
def doctor_patients():
    out = []
    for sid, s in SESSIONS.items():
        analysis = analyze(s["scores"], s["active"])
        out.append({
            "session_id": sid, "name": s["name"], "created": s["created"], "updated": s["updated"],
            "n_messages": len(s["scores"]), "index": analysis["index"],
            "active_alerts": [{"axis": a["axis"], "label": a["label"], "critical": a["critical"]}
                              for a in analysis["alerts"]],
            "unseen_alerts": sum(1 for a in s["alert_log"] if not a["seen"]),
            "critical": any(a["critical"] for a in analysis["alerts"]),
        })
    out.sort(key=lambda p: p["updated"], reverse=True)
    return out


@app.get("/api/doctor/patient/{sid}")
def doctor_patient(sid: str):
    if sid not in SESSIONS:
        raise HTTPException(404, "unknown session")
    s = SESSIONS[sid]
    for a in s["alert_log"]:
        a["seen"] = True
    return {**_state(sid, s), "name": s["name"], "context": s["context"],
            "created": s["created"], "updated": s["updated"],
            "convo": s["convo"], "alert_log": s["alert_log"]}


@app.get("/api/doctor/alerts")
def doctor_alerts():
    total_unseen = sum(sum(1 for a in s["alert_log"] if not a["seen"]) for s in SESSIONS.values())
    return {"unseen": total_unseen}


# ---------------------------------------------------------------- pages

@app.get("/")
def index():
    return FileResponse(HERE / "static" / "index.html")


@app.get("/patient")
def patient_page():
    return FileResponse(HERE / "static" / "patient.html")


@app.get("/doctor")
def doctor_page():
    return FileResponse(HERE / "static" / "doctor.html")


app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")


# ---------------------------------------------------------------- demo seeding

CANNED_REPLIES = [
    "Merci de partager cela avec moi. Comment vous sentez-vous aujourd'hui ?",
    "Je comprends, c'est tout à fait normal d'avoir cette inquiétude. Voulez-vous m'en dire plus ?",
    "C'est une bonne nouvelle que vous ayez pu vous reposer. Qu'est-ce qui vous a aidé ?",
    "Je vous entends, cela semble difficile. Essayez peut-être quelques respirations profondes ce soir.",
    "Le manque de sommeil pèse beaucoup. Un horaire de coucher régulier pourrait vous aider, doucement.",
    "Merci de me le confier. Garder un lien, même court, avec un proche peut faire du bien.",
    "Je suis là pour vous écouter. Qu'est-ce qui vous a semblé le plus lourd aujourd'hui ?",
    "Vous n'êtes pas seul(e). Je vous encourage à en parler à votre médecin ; le 3114 est là 24h/24.",
]


def _seed_patient(name: str, context: str, messages: list[str], days: int):
    sid, s = _session(None, context, None, name)
    base = datetime.now() - timedelta(days=days)
    step = timedelta(days=days / max(len(messages), 1))
    for i, m in enumerate(messages):
        ts = (base + step * i).isoformat(timespec="seconds")
        s["convo"].append({"role": "user", "content": m, "ts": ts})
        s["scores"].append(scorer.score(m))
        s["expl"].append(scorer.explain(m))
        analysis = analyze(s["scores"], s["active"])
        for a in _log_new_alerts(s, analysis, m):
            a["ts"] = ts
        s["convo"].append({"role": "assistant", "content": CANNED_REPLIES[i % len(CANNED_REPLIES)], "ts": ts})
        s["updated"] = ts
    return sid


def seed_demo():
    d = json.loads((HERE / "demo_journey.json").read_text())
    _seed_patient("Léa Martin", d["context"], d["messages"], days=8)
    _seed_patient(
        "Karim Benali",
        "Patient de 41 ans, suivi post-burn-out en phase de reprise. Surveiller le sommeil et l'anxiété.",
        [
            "Bonjour, la reprise à mi-temps s'est bien passée cette semaine, je suis content.",
            "J'ai bien dormi presque toutes les nuits, juste un réveil un peu tôt lundi.",
            "J'ai repris la course à pied avec un collègue, ça m'a fait beaucoup de bien.",
            "Un peu de stress avant la réunion de jeudi, mais c'est passé rapidement.",
            "Week-end en famille très agréable, je me sens plus solide qu'avant.",
        ],
        days=6,
    )


seed_demo()


def main() -> None:
    import uvicorn
    uvicorn.run("hackpsyassistant.api:app", host="127.0.0.1", port=8000, reload=False)
