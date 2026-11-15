"""Three-tier attention classification, derived from the existing (non-diagnostic) risk index
and active trend alerts. Used by the doctor to decide, patient by patient, which features to open
up — e.g. whether a stable patient may see a recovered peer mentor. Never shown to the patient
in these words; it is a triage aid for the doctor, not a label.
"""
from __future__ import annotations

TIERS = {
    "leger": {"label": "Suivi léger", "order": 0, "color": "#18a877"},
    "modere": {"label": "Suivi renforcé", "order": 1, "color": "#e8872f"},
    "vigilance": {"label": "Vigilance rapprochée", "order": 2, "color": "#e5484d"},
}


def classify(index: float, alerts: list[dict]) -> dict:
    critical = any(a.get("critical") for a in alerts)
    if critical or index >= 0.55:
        key = "vigilance"
    elif alerts or index >= 0.28:
        key = "modere"
    else:
        key = "leger"
    return {"key": key, **TIERS[key]}
