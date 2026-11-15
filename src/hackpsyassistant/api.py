"""FastAPI app: patient chat (text + audio), doctor dashboard, alerts, and the JSON API."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import engagement, events, gad7, llm
from .config import AXES, DIAGNOSTIC_DISCLAIMER
from .scorer import load_scorer
from .tiers import classify
from .trajectory import analyze

HERE = Path(__file__).parent
app = FastAPI(title="HackPsyAssistant")
scorer = load_scorer()
SESSIONS: dict[str, dict] = {}
PEER_MSGS: dict[tuple[str, str], list[dict]] = {}


def _peer_key(a: str, b: str) -> tuple[str, str]:
    return tuple(sorted((a, b)))


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _session(sid: str | None, context: str | None = None, active: list[str] | None = None,
             name: str | None = None) -> tuple[str, dict]:
    sid = sid or uuid.uuid4().hex[:8]
    s = SESSIONS.setdefault(sid, {
        "name": name or "Patient anonyme", "context": "", "active": list(AXES),
        "convo": [], "scores": [], "expl": [], "alert_log": [], "events": [], "mentor": False,
        "mentor_visible": False, "assigned_mentor": None, "mentees": [], "gad7": [],
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


def _log_events(s: dict, message: str, ts: str) -> list[dict]:
    found = events.detect(message)
    for e in found:
        entry = {**e, "ts": ts, "msg_index": len(s["scores"]), "quote": message}
        s["events"].append(entry)
    return found


def _peak_levels(s: dict) -> dict:
    """Peak (not just current) level per axis — used for peer/mentor matching so a recovered
    mentor's *history* of having struggled still counts, even though they're stable now."""
    series = analyze(s["scores"], s["active"])["series"]
    return {ax: {"level": max(ser["ema"]) if ser["ema"] else 0.0} for ax, ser in series.items()}


# ---------------------------------------------------------------- patient API

@app.get("/api/config")
def config():
    return {"axes": AXES, "scorer": scorer.name, "llm": llm.MODEL, "disclaimer": DIAGNOSTIC_DISCLAIMER}


@app.post("/api/session")
def session(body: SessionIn):
    sid, s = _session(body.session_id, body.context, body.axes, body.patient_name)
    s["updated"] = _now()
    return _state(sid, s)


@app.post("/api/chat")
def chat(body: ChatIn):
    sid, s = _session(body.session_id, body.context, body.axes, body.patient_name)
    ts = _now()
    s["convo"].append({"role": "user", "content": body.message, "ts": ts})
    s["scores"].append(scorer.score(body.message))
    s["expl"].append(scorer.explain(body.message))
    _log_events(s, body.message, ts)
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


class GAD7In(BaseModel):
    session_id: str
    answers: list[int]


@app.post("/api/gad7")
def submit_gad7(body: GAD7In):
    sid, s = _session(body.session_id)
    try:
        sc = gad7.score(body.answers)
    except ValueError as e:
        raise HTTPException(400, str(e))
    band = gad7.band_for(sc)
    entry = {"ts": _now(), "answers": body.answers, "score": sc, "band": band}
    s["gad7"].append(entry)
    s["updated"] = _now()
    if sc >= gad7.ALERT_THRESHOLD:
        s["alert_log"].append({
            "axis": "gad7", "label": "Auto-évaluation GAD-7 au-dessus du seuil usuel", "critical": False,
            "level": sc / 21, "slope": 0.0,
            "recommendation": "Score auto-déclaré par le patient — à discuter en consultation.",
            "ts": entry["ts"], "msg_index": len(s["scores"]), "message": f"Score GAD-7 : {sc}/21", "seen": False,
        })
    return {"score": sc, "band": band, "streak": gad7.streak_minime_or_leger(s["gad7"]),
            "history": s["gad7"], "items": gad7.ITEMS, "scale": gad7.SCALE}


@app.get("/api/gad7/{sid}")
def get_gad7(sid: str):
    if sid not in SESSIONS:
        raise HTTPException(404, "unknown session")
    s = SESSIONS[sid]
    return {"history": s["gad7"], "streak": gad7.streak_minime_or_leger(s["gad7"]),
            "items": gad7.ITEMS, "scale": gad7.SCALE}


# ---------------------------------------------------------------- peer mentoring (patient-facing)

@app.get("/api/peer/info")
def peer_info(sid: str):
    if sid not in SESSIONS:
        raise HTTPException(404, "unknown session")
    s = SESSIONS[sid]
    mentor = None
    if s.get("mentor_visible") and s.get("assigned_mentor") in SESSIONS:
        m = SESSIONS[s["assigned_mentor"]]
        mentor = {"sid": s["assigned_mentor"], "name": m["name"]}
    mentees = [{"sid": msid, "name": SESSIONS[msid]["name"]} for msid in s.get("mentees", []) if msid in SESSIONS]
    return {"mentor": mentor, "mentees": mentees, "is_mentor": s.get("mentor", False)}


def _assert_linked(a: str, b: str):
    if a not in SESSIONS or b not in SESSIONS:
        raise HTTPException(404, "unknown session")
    sa, sb = SESSIONS[a], SESSIONS[b]
    linked = sa.get("assigned_mentor") == b or sb.get("assigned_mentor") == a
    if not linked:
        raise HTTPException(403, "ce lien n'a pas été approuvé par le médecin")


@app.get("/api/peer/thread")
def peer_thread(me: str, with_sid: str = Query(..., alias="with")):
    _assert_linked(me, with_sid)
    return {"messages": PEER_MSGS.get(_peer_key(me, with_sid), [])}


class PeerSendIn(BaseModel):
    me: str
    to: str
    text: str


@app.post("/api/peer/send")
def peer_send(body: PeerSendIn):
    _assert_linked(body.me, body.to)
    key = _peer_key(body.me, body.to)
    PEER_MSGS.setdefault(key, []).append({"from": body.me, "text": body.text, "ts": _now()})
    return {"ok": True}


class ApproveMentorIn(BaseModel):
    session_id: str
    mentor_session_id: str | None = None


@app.post("/api/doctor/approve-mentor")
def approve_mentor(body: ApproveMentorIn):
    if body.session_id not in SESSIONS:
        raise HTTPException(404, "unknown session")
    s = SESSIONS[body.session_id]
    old_mentor = s.get("assigned_mentor")
    if old_mentor and old_mentor in SESSIONS and body.session_id in SESSIONS[old_mentor].get("mentees", []):
        SESSIONS[old_mentor]["mentees"].remove(body.session_id)
    if body.mentor_session_id:
        if body.mentor_session_id not in SESSIONS:
            raise HTTPException(404, "mentor inconnu")
        s["assigned_mentor"] = body.mentor_session_id
        s["mentor_visible"] = True
        mentees = SESSIONS[body.mentor_session_id].setdefault("mentees", [])
        if body.session_id not in mentees:
            mentees.append(body.session_id)
    else:
        s["assigned_mentor"] = None
        s["mentor_visible"] = False
    return {"ok": True, "assigned_mentor": s["assigned_mentor"], "mentor_visible": s["mentor_visible"]}


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
        eng = engagement.engagement_stats(s["convo"])
        out.append({
            "session_id": sid, "name": s["name"], "created": s["created"], "updated": s["updated"],
            "n_messages": len(s["scores"]), "index": analysis["index"], "mentor": s.get("mentor", False),
            "tier": classify(analysis["index"], analysis["alerts"]),
            "mentor_visible": s.get("mentor_visible", False),
            "assigned_mentor_name": SESSIONS.get(s.get("assigned_mentor") or "", {}).get("name"),
            "active_alerts": [{"axis": a["axis"], "label": a["label"], "critical": a["critical"]}
                              for a in analysis["alerts"]],
            "unseen_alerts": sum(1 for a in s["alert_log"] if not a["seen"]),
            "critical": any(a["critical"] for a in analysis["alerts"]),
            "days_since_last": eng["days_since_last"], "engagement_trend": eng["trend"],
            "n_events": len(s["events"]), "latest_gad7": s["gad7"][-1] if s["gad7"] else None,
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
    analysis = analyze(s["scores"], s["active"])
    others = [{"sid": osid, "name": o["name"], "mentor": o.get("mentor", False),
               "n_messages": len(o["scores"]), "levels": _peak_levels(o)}
              for osid, o in SESSIONS.items() if osid != sid]
    peers = engagement.suggest_peers(sid, analysis["levels"], others)
    mentees = [{"sid": m, "name": SESSIONS[m]["name"]} for m in s.get("mentees", []) if m in SESSIONS]
    return {**_state(sid, s), "name": s["name"], "context": s["context"],
            "created": s["created"], "updated": s["updated"],
            "convo": s["convo"], "alert_log": s["alert_log"], "events": s["events"],
            "mentor": s.get("mentor", False), "engagement": engagement.engagement_stats(s["convo"]),
            "peers": peers, "tier": classify(analysis["index"], analysis["alerts"]),
            "mentor_visible": s.get("mentor_visible", False), "assigned_mentor": s.get("assigned_mentor"),
            "mentees": mentees, "gad7": s["gad7"]}


@app.get("/api/doctor/alerts")
def doctor_alerts():
    total_unseen = sum(sum(1 for a in s["alert_log"] if not a["seen"]) for s in SESSIONS.values())
    return {"unseen": total_unseen}


class MentorIn(BaseModel):
    session_id: str
    mentor: bool


@app.post("/api/doctor/mentor")
def set_mentor(body: MentorIn):
    if body.session_id not in SESSIONS:
        raise HTTPException(404, "unknown session")
    SESSIONS[body.session_id]["mentor"] = body.mentor
    return {"ok": True, "mentor": body.mentor}


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


def _seed_patient(name: str, context: str, messages: list[str], days: int, mentor: bool = False) -> str:
    sid, s = _session(None, context, None, name)
    s["mentor"] = mentor
    base = datetime.now() - timedelta(days=days)
    step = timedelta(days=days / max(len(messages), 1))
    for i, m in enumerate(messages):
        ts = (base + step * i).isoformat(timespec="seconds")
        s["convo"].append({"role": "user", "content": m, "ts": ts})
        s["scores"].append(scorer.score(m))
        s["expl"].append(scorer.explain(m))
        _log_events(s, m, ts)
        analysis = analyze(s["scores"], s["active"])
        for a in _log_new_alerts(s, analysis, m):
            a["ts"] = ts
        s["convo"].append({"role": "assistant", "content": CANNED_REPLIES[i % len(CANNED_REPLIES)], "ts": ts})
        s["updated"] = ts
    return sid


def seed_demo():
    d = json.loads((HERE / "demo_journey.json").read_text())
    _seed_patient("Léa Martin", d["context"], d["messages"], days=8)

    # Karim: a recovery arc (struggled, then improved) -> flagged as a volunteer peer mentor.
    _seed_patient(
        "Karim Benali",
        "Patient de 41 ans, suivi post-burn-out en phase de reprise. Surveiller le sommeil et l'anxiété.",
        [
            "La reprise à mi-temps m'angoisse un peu, j'ai peur de ne pas être à la hauteur.",
            "J'ai mal dormi cette nuit, je repensais sans arrêt à l'ancien rythme de travail.",
            "Petit à petit ça va mieux, j'ai réussi à décrocher du travail hier soir.",
            "J'ai repris la course à pied avec un collègue, ça m'a fait beaucoup de bien.",
            "Je dors beaucoup mieux maintenant, presque comme avant le burn-out.",
            "Je me sens vraiment plus solide. Je pense que je pourrais aider quelqu'un qui traverse la même chose.",
        ],
        days=6, mentor=True,
    )

    # Nadia: currently going through a similar overload -> will be matched to Karim, and
    # demonstrates the declared-events timeline (treatment interruption + substance use).
    _seed_patient(
        "Nadia Chraibi",
        "Patiente de 28 ans, surcharge professionnelle récente. Surveiller l'anxiété et le sommeil.",
        [
            "Depuis deux semaines j'ai énormément de dossiers en retard, je stresse dès le matin.",
            "Je dors très mal, je me réveille en pensant au travail.",
            "J'ai arrêté de prendre mon traitement pour le sommeil cette semaine, je ne sais pas si c'est une bonne idée.",
            "Je suis épuisée et de plus en plus anxieuse, même le week-end je n'arrive pas à décrocher.",
            "J'ai recommencé à fumer pour tenir le choc au travail, je culpabilise un peu.",
            "Je me sens vraiment débordée, j'ai l'impression de ne plus avoir de contrôle.",
        ],
        days=5,
    )


def _seed_extras():
    by_name = {s["name"]: sid for sid, s in SESSIONS.items()}
    karim, nadia = by_name["Karim Benali"], by_name["Nadia Chraibi"]

    # Doctor already approved Nadia to see Karim as her peer mentor, with one opening exchange.
    SESSIONS[nadia]["assigned_mentor"] = karim
    SESSIONS[nadia]["mentor_visible"] = True
    SESSIONS[karim]["mentees"] = [nadia]
    key = _peer_key(karim, nadia)
    t0 = datetime.now() - timedelta(days=2)
    PEER_MSGS[key] = [
        {"from": karim, "text": "Bonjour Nadia, le Dr m'a parlé de vous — j'ai traversé une période un peu similaire. Je suis là si vous voulez en parler.", "ts": t0.isoformat(timespec="seconds")},
        {"from": nadia, "text": "Merci beaucoup, ça me touche. C'est vrai que ça fait du bien de parler à quelqu'un qui comprend vraiment.", "ts": (t0 + timedelta(hours=3)).isoformat(timespec="seconds")},
    ]

    # Karim's own GAD-7 history: a motivating downward trend (he's the recovered mentor).
    base = datetime.now() - timedelta(days=21)
    for i, sc in enumerate([13, 9, 6, 3]):
        ts = (base + timedelta(days=7 * i)).isoformat(timespec="seconds")
        SESSIONS[karim]["gad7"].append({"ts": ts, "answers": [sc // 7] * 7, "score": sc, "band": gad7.band_for(sc)})


seed_demo()
_seed_extras()


def main() -> None:
    import uvicorn
    uvicorn.run("hackpsyassistant.api:app", host="127.0.0.1", port=8000, reload=False)
