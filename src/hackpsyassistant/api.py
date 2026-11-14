"""FastAPI app: serves the demo UI and the JSON API."""
from __future__ import annotations

import json
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
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


def _session(sid: str | None, context: str | None = None, active: list[str] | None = None) -> tuple[str, dict]:
    sid = sid or uuid.uuid4().hex[:8]
    s = SESSIONS.setdefault(sid, {"context": "", "active": list(AXES), "convo": [], "scores": [], "expl": []})
    if context is not None:
        s["context"] = context
    if active:
        s["active"] = [a for a in active if a in AXES]
    return sid, s


class ChatIn(BaseModel):
    session_id: str | None = None
    message: str
    context: str | None = None
    axes: list[str] | None = None


class SessionIn(BaseModel):
    session_id: str | None = None
    context: str | None = None
    axes: list[str] | None = None


def _state(sid: str, s: dict) -> dict:
    return {"session_id": sid, "scorer": scorer.name, "axes": {a: AXES[a] for a in s["active"]},
            "analysis": analyze(s["scores"], s["active"]), "explanations": s["expl"]}


@app.get("/api/config")
def config():
    return {"axes": AXES, "scorer": scorer.name, "llm": llm.MODEL}


@app.post("/api/session")
def session(body: SessionIn):
    sid, s = _session(body.session_id, body.context, body.axes)
    return _state(sid, s)


@app.post("/api/score")
def score_only(body: ChatIn):
    return {"scores": scorer.score(body.message), "explanation": scorer.explain(body.message)}


@app.post("/api/chat")
def chat(body: ChatIn):
    sid, s = _session(body.session_id, body.context, body.axes)
    s["convo"].append({"role": "user", "content": body.message})
    s["scores"].append(scorer.score(body.message))
    s["expl"].append(scorer.explain(body.message))
    analysis = analyze(s["scores"], s["active"])
    reply, src = llm.chat_reply(s["context"], s["convo"], analysis)
    s["convo"].append({"role": "assistant", "content": reply})
    return {**_state(sid, s), "reply": reply, "reply_source": src}


@app.post("/api/summary")
def summary(body: SessionIn):
    if not body.session_id or body.session_id not in SESSIONS:
        raise HTTPException(404, "unknown session")
    s = SESSIONS[body.session_id]
    text, src = llm.summarize(s["context"], s["convo"], analyze(s["scores"], s["active"]))
    return {"summary": text, "source": src}


@app.get("/api/demo")
def demo():
    return json.loads((HERE / "demo_journey.json").read_text())


@app.get("/")
def index():
    return FileResponse(HERE / "static" / "index.html")


app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")


def main() -> None:
    import uvicorn
    uvicorn.run("hackpsyassistant.api:app", host="127.0.0.1", port=8000, reload=False)
