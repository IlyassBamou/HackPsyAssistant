"""FastAPI entry point: mounts the API routers and serves the demo UI."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .routes import alerts, analysis, chat, patients, reports
from .services.conversation_orchestrator import PatientNotFound

HERE = Path(__file__).parent
app = FastAPI(title="HackPsyAssistant")

for r in (chat, analysis, alerts, patients, reports):
    app.include_router(r.router)


@app.exception_handler(PatientNotFound)
def patient_not_found(request: Request, exc: PatientNotFound):
    return JSONResponse({"detail": f"unknown patient {exc.args[0]!r}"}, status_code=404)


@app.get("/")
def index():
    return FileResponse(HERE / "static" / "index.html")


app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")


def main() -> None:
    import uvicorn
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
